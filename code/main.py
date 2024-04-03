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

window = pygame.display.set_mode(SCREEN_SIZE)
player_image = pygame.transform.smoothscale_by(pygame.image.load("assets/swordfish.png").convert_alpha(), 0.25)

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
        
        self.image = player_image
        self.rect = self.image.get_rect(center = position)
        self.position = pygame.Vector2(position)

        self.speed = 1.5

        self.velocity = pygame.Vector2()

        self.in_water = True

    def update(self):
        # move towards mouse
        camera = self.manager.get("camera")
        dv: pygame.Vector2 = camera.screen_to_world(pygame.mouse.get_pos()) - self.position

        if pygame.mouse.get_pressed()[0] and self.rect.centery >= 0:
            dv.scale_to_length(self.speed)
            self.velocity += dv

        # check for in water
        now_in_water = True
        if self.rect.centery < 0:
            now_in_water = False

        # when entering water
        if now_in_water and not self.in_water:
            self.manager.get("ocean").add_wave(self.rect.centerx)

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

        # clamp velocity
        if -0.001 < self.velocity.x < 0.001: self.velocity.x = 0
        if -0.001 < self.velocity.y < 0.001: self.velocity.y = 0

        self.position += self.velocity

        # look towards
        self.direction = math.atan2(self.velocity.y, self.velocity.x)
        image_used = player_image
        if self.direction > HALF_PI or self.direction < -HALF_PI:
            image_used = pygame.transform.flip(image_used, False, True)

        self.image = pygame.transform.rotate(image_used, -math.degrees(self.direction))
        self.rect = self.image.get_rect()

        self.rect.center = self.position

        self.in_water = now_in_water

class WaterSpring(Sprite):
    def __init__(self, manager):
        super().__init__(manager)

class Ocean(Sprite):
    def __init__(self, manager, layer_height: int):
        super().__init__(manager, ["update"])
        self.id = "ocean"

        self.colour = (0, 0, 0)
        self.layer_height = layer_height
        
        self.colour_palette = [
            (65, 185, 238),
        ]

    def add_wave(self, position: float):
        pass

    def update(self):
        player = self.manager.get("player")

        current_layer = min(max(0, int(player.rect.y // LAYER_HEIGHT)), len(self.colour_palette) - 1)

        self.colour = self.colour_palette[current_layer]

    def render(self, surface):
        surface.fill(self.colour)

class Sky(Sprite):
    def __init__(self, manager):
        super().__init__(manager)
        self.image = pygame.Surface((SCREEN_SIZE.x * 2, SCREEN_SIZE.y * 2))
        self.image.fill((197, 240, 251))
        self.rect = self.image.get_rect(bottom = 0)
    
    def update(self):
        self.rect.centerx = self.manager.get("player").rect.centerx

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

        self.background = self.manager.add(Ocean(self.manager, LAYER_HEIGHT))
        self.sky = self.manager.add(Sky(self.manager))
        self.player = self.manager.add(Player(self.manager, SCREEN_SIZE / 2))
        self.camera = self.manager.add(Camera(self.manager, self.player))

    def update(self):
        self.manager.update_group.update()

    def render(self, surface: pygame.Surface):
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

    pygame.quit()

if __name__ == "__main__":
    main()
