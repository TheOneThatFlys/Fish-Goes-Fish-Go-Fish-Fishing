from __future__ import annotations

import math
import pygame
import random
from typing import TypeVar, Literal

pygame.init()

Vec2 = tuple[float, float]
Colour = tuple[int, int, int]

SCREEN_SIZE = pygame.Vector2(1280, 720)
FPS = 60
LAYER_HEIGHT = SCREEN_SIZE.y * 2
HALF_PI = math.pi / 2
ANIMATION_TIME = 10

window = pygame.display.set_mode(SCREEN_SIZE)

def lerp(start, end, a):
    return (1 - a) * start + a * end

class Sprite(pygame.sprite.Sprite):
    def __init__(self, manager: ObjectManager, groups: list[Literal["render", "update"]] = ["render", "update"]):
        super().__init__()
        self.manager = manager
        self.group_keys = groups
        self.id = ""

class Camera(Sprite):
    def __init__(self, manager, target: Sprite):
        super().__init__(manager, ["update"])
        self.id = "camera"

        self.target = target
        self.position = pygame.Vector2(target.rect.center)

        self.half_screen_size = SCREEN_SIZE / 2

    def update(self):
        # move towards target with smoothing
        self.position += (self.target.rect.center - self.position) * 0.2

    def world_to_screen(self, coords: Vec2) -> Vec2:
        return coords - self.position + self.half_screen_size
    
    def screen_to_world(self, coords: Vec2) -> Vec2:
        return coords + self.position - self.half_screen_size

    def render(self, surface: pygame.Surface, group: pygame.sprite.Group):
        offset = pygame.Vector2(
            int(self.position.x) - self.half_screen_size.x,
            int(self.position.y) - self.half_screen_size.y
        )

        for item in group.sprites():
            surface.blit(item.image, item.rect.topleft - offset)

class Player(Sprite):
    def __init__(self, manager, position):
        super().__init__(manager)
        self.id = "player"
        
        self.animation_frames = []
        self.current_index = 0
        self.animation_counter = 0
        for i in range(2):
            self.animation_frames.append(pygame.transform.scale_by(pygame.image.load(f"assets/swordfish_{i}.png").convert_alpha(), 0.25))

        self.image = self.animation_frames[0]
        self.rect = self.image.get_rect(center = position)
        self.position = pygame.Vector2(position)
        self.direction = 0

        self.speed = 1.5

        self.velocity = pygame.Vector2()

        self.in_water = True

    def update_animations(self):
        self.animation_counter += 1
        if self.animation_counter >= ANIMATION_TIME:
            self.current_index += 1
            if self.current_index == len(self.animation_frames):
                self.current_index = 0
            self.animation_counter = 0

    def update(self):

        # move towards mouse
        camera = self.manager.get("camera")
        dv: pygame.Vector2 = camera.screen_to_world(pygame.mouse.get_pos()) - self.position

        if pygame.mouse.get_pressed()[0] and self.rect.centery >= 0:
            self.update_animations()
            dv.scale_to_length(self.speed)
            self.velocity += dv

        # check for in water
        now_in_water = True
        if self.rect.centery < 0:
            now_in_water = False

        # when entering water
        if now_in_water and not self.in_water:
            self.manager.get("ocean").splash(self.rect.centerx, lerp(0, 10, min(abs(self.velocity.y), 30) / 30))
        
        # when exiting water
        if not now_in_water and self.in_water:
            self.manager.get("ocean").splash(self.rect.centerx, lerp(0, -10, min(abs(self.velocity.y), 30) / 30))

        # apply gravity
        if not now_in_water:
            self.velocity.y += 0.7
        else:
            # apply drag only in water
            self.velocity *= 0.95

        # when going out of water
        if not now_in_water and self.in_water:
            if self.velocity.y > 2:
                self.velocity.y = 0

        self.position += self.velocity

        if self.velocity.magnitude() < 0.01:
            self.velocity = pygame.Vector2(0, 0)

        # look towards
        if self.velocity.magnitude() != 0:
            self.direction = math.atan2(self.velocity.y, self.velocity.x)

        image_used = self.animation_frames[self.current_index]
        if self.direction > HALF_PI or self.direction < -HALF_PI:
            image_used = pygame.transform.flip(image_used, False, True)

        self.image = pygame.transform.rotate(image_used, -math.degrees(self.direction))

        self.rect = self.image.get_rect()

        self.rect.center = self.position

        self.in_water = now_in_water

class WaterSpring(Sprite):
    def __init__(self, manager, position: Vec2, spring_constant: float, dampening: float):
        super().__init__(manager, ["update"])

        self.extension = 0
        self.origin = position[1]

        self.spring_constant = spring_constant
        self.dampening = dampening

        self.velocity = 0
        self.force = 0

        self.image = pygame.Surface((4, 4))
        self.rect = self.image.get_rect(center = position)

    def update(self):
        force = -self.extension * self.spring_constant - self.velocity * self.dampening
        self.velocity += force
        self.extension += self.velocity

        self.rect.centery = self.origin + self.extension

class Ocean(Sprite):
    def __init__(self, manager, layer_height: int):
        super().__init__(manager, ["update"])
        self.id = "ocean"

        self.colour = (0, 0, 0)
        self.layer_height = layer_height
        
        self.colour_palette = [
            (65, 185, 238),
        ]

        self.target_wave_height = 80
        self.player: Player = self.manager.get("player")
        self.camera: Camera = self.manager.get("camera")

        self.wave_interval = 8
        self.spread = 0.1 / self.wave_interval
        self.passes = 8
        self.add_springs()

    def add_springs(self):
        self.springs: dict[int, WaterSpring] = {}
        for i in range(0, int(SCREEN_SIZE.x * 2), self.wave_interval):
            self.add_spring(i)

    def update_springs(self):
        for _ in range(self.passes):
            for i, spring in self.springs.items():
                left_neighbour = self.springs.get(i - self.wave_interval, None)
                right_neighbour = self.springs.get(i + self.wave_interval, None)

                if left_neighbour:
                    left_neighbour.velocity += self.spread * (spring.extension - left_neighbour.extension)

                if right_neighbour:
                    right_neighbour.velocity += self.spread * (spring.extension - right_neighbour.extension)

    def add_spring(self, position: int):
        spring = WaterSpring(self.manager, (position, 0), 0.015, 0.03)
        self.springs[position] = spring
        self.manager.add(spring)

    def add_more_springs(self):
        left_most_point = min(self.springs.keys())
        right_most_point = max(self.springs.keys())

        while left_most_point > self.player.rect.centerx - SCREEN_SIZE.x:
            pos = left_most_point - self.wave_interval
            self.add_spring(pos)
            left_most_point = pos

        while left_most_point < self.player.rect.centerx - SCREEN_SIZE.x:
            spring = self.springs[left_most_point]
            spring.kill()
            del self.springs[left_most_point]
            left_most_point += self.wave_interval
        
        while right_most_point < self.player.rect.centerx + SCREEN_SIZE.x:
            pos = right_most_point + self.wave_interval
            self.add_spring(pos)
            right_most_point = pos

        while right_most_point > self.player.rect.centerx + SCREEN_SIZE.x:
            spring = self.springs[right_most_point]
            spring.kill()
            del self.springs[right_most_point]
            right_most_point -= self.wave_interval

    def splash(self, position: float, speed: float, size: int = 4):
        original_index = int(position // self.wave_interval * self.wave_interval)
        for i in range(original_index - size * self.wave_interval, original_index + size * self.wave_interval, self.wave_interval):
            spring = self.springs.get(i, None)
            if spring:
                velocity = lerp(speed, 0, abs(original_index - i) / (size * self.wave_interval))

                spring.velocity += velocity

    def draw_waves(self, surface: pygame.Surface):
        points = []
        for x, spring in self.springs.items():
            points.append(self.camera.world_to_screen((x, spring.origin + spring.extension)))

        points.sort(key = lambda point: point.x)

        points.insert(0, (0, SCREEN_SIZE.y))
        points.append((SCREEN_SIZE.x, SCREEN_SIZE.y))

        pygame.draw.polygon(surface, self.colour, points)

        pygame.draw.lines(surface, (255, 255, 255), False, points[1:-2], width = 3)

    def update(self):
        current_layer = min(max(0, int(self.player.rect.y // LAYER_HEIGHT)), len(self.colour_palette) - 1)

        self.colour = self.colour_palette[current_layer]
        self.add_more_springs()
        self.update_springs()

    def render(self, surface):
        covered_rect = pygame.Rect(0, max(self.manager.get("camera").world_to_screen(pygame.Vector2(0, 0)).y + self.target_wave_height, 0), *SCREEN_SIZE)
        # surface.fill(self.colour, covered_rect)

        self.draw_waves(surface)

T = TypeVar("T", bound = Sprite)
class ObjectManager:
    def __init__(self):
        self.objects = {}
        self.render_group = pygame.sprite.Group()
        self.update_group = pygame.sprite.Group()

    def get(self, key: str):
        return self.objects[key]
    
    def add(self, sprite: T) -> T:
        if sprite.id != "":
            self.objects[sprite.id] = sprite
        
        if "render" in sprite.group_keys:
            self.render_group.add(sprite)
        if "update" in sprite.group_keys:
            self.update_group.add(sprite)

        return sprite
    
    def add_obj(self, obj, key):
        self.objects[key] = obj
        return obj

class FishLevel:
    def __init__(self):
        self.manager = ObjectManager()
        self.manager.add_obj(self, "level")

        self.player = self.manager.add(Player(self.manager, SCREEN_SIZE / 2))
        self.camera = self.manager.add(Camera(self.manager, self.player))
        self.background = self.manager.add(Ocean(self.manager, LAYER_HEIGHT))

    def update(self):
        self.manager.update_group.update()

    def render(self, surface: pygame.Surface):
        surface.fill((197, 240, 251))
        self.background.render(surface)
        self.camera.render(surface, self.manager.render_group)

def main():
    clock = pygame.time.Clock()

    pygame.display.set_caption("Fish Goes Fish Go Fish Fishing")
    pygame.display.set_icon(pygame.image.load("assets/icon.png"))

    running = True

    test_level = FishLevel()

    while running:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        window.fill((0, 0, 0))

        test_level.update()
        test_level.render(window)

        pygame.display.update()

        # print(clock.get_fps())

    pygame.quit()

if __name__ == "__main__":
    main()
