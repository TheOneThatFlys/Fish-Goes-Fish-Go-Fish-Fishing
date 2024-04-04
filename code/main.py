from __future__ import annotations

import math
import pygame
import random
from typing import TypeVar, Literal

pygame.init()

Vec2 = tuple[float, float]
Colour = tuple[int, int, int]
Group = Literal["render", "update", "collide", "enemy"]
Axis = Literal["x", "y"]

SCREEN_SIZE = pygame.Vector2(1280, 720)
FPS = 60
LAYER_HEIGHT = SCREEN_SIZE.y * 2
HALF_PI = math.pi / 2
ANIMATION_TIME = 10

WORLD_LEFT = 0
WORLD_RIGHT = LAYER_HEIGHT * 10
WORLD_BOTTOM = LAYER_HEIGHT * 5

COLOUR_BEACH = (193, 149, 75)
COLOUR_BORDER = (154, 110, 39)

def lerp(start: float, end: float, a: float):
    return (1 - a) * start + a * end

def lerp_colour(start: Colour, end: Colour, a: float):
    return (lerp(start[0], end[0], a), lerp(start[1], end[1], a), lerp(start[2], end[2], a))

def draw_gradient(surface: pygame.Surface, start_colour: Colour, end_colour: Colour) -> pygame.Surface:
    """Draw vertical gradient onto surface. Modifies original surface."""
    width, height = surface.get_size()
    for i in range(height):
        t = i / height
        colour = lerp_colour(start_colour, end_colour, t)

        pygame.draw.line(surface, colour, (0, i), (width, i))
    return surface

class Sprite(pygame.sprite.Sprite):
    def __init__(self, manager: ObjectManager, groups: list[Group] = ["render", "update"]):
        super().__init__()
        self.manager = manager
        self.group_keys = groups
        self.id = ""
        self.z_index = 0

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

        for item in sorted(group.sprites(), key = lambda sprite: sprite.z_index):
            surface.blit(item.image, item.rect.topleft - offset)

class Player(Sprite):
    def __init__(self, manager: ObjectManager, initial_velocity: Vec2 = (0, 0)):
        super().__init__(manager)
        self.id = "player"
        self.z_index = 1
        
        self.animation_frames = []
        self.current_index = 0
        self.animation_counter = 0
        for i in range(2):
            self.animation_frames.append(pygame.transform.scale_by(pygame.image.load(f"assets/swordfish_{i}.png").convert_alpha(), 0.25))

        self.image = self.animation_frames[0]
        self.rect = self.image.get_frect(bottom = self.manager.get("left-wall").rect.top, left = 0)
        self.direction = 0

        self.speed = 1.5

        self.velocity = pygame.Vector2(initial_velocity)

        self.in_water = self.rect.centery > 0
        self.time_since_in_air = 0 if self.in_water else 100

        self.splash_sound = pygame.mixer.Sound("assets/splash.mp3")
        self.small_splash_sound = pygame.mixer.Sound("assets/small_splash.mp3")
        self.splash_sound.set_volume(0.3)
        self.small_splash_sound.set_volume(0.3)

    def update_animations(self):
        self.animation_counter += 1
        if self.animation_counter >= ANIMATION_TIME:
            self.current_index += 1
            if self.current_index == len(self.animation_frames):
                self.current_index = 0
            self.animation_counter = 0

    def ammend_collisions(self, future_rect: pygame.Rect):
        if future_rect.x < WORLD_LEFT:
            future_rect.x = WORLD_LEFT
        if future_rect.right > WORLD_RIGHT:
            future_rect.right = WORLD_RIGHT
        if future_rect.bottom > WORLD_BOTTOM:
            future_rect.bottom = WORLD_BOTTOM

    def update(self):
        # move towards mouse
        camera = self.manager.get("camera")
        dv: pygame.Vector2 = camera.screen_to_world(pygame.mouse.get_pos()) - self.rect.center

        if pygame.mouse.get_pressed()[0] and self.rect.centery >= 0 and self.time_since_in_air >= 5:
            self.update_animations()
            if dv.magnitude() > 5:
                mvm = dv.copy()
                mvm.scale_to_length(self.speed)
                self.velocity += mvm

        # check for in water
        now_in_water = True
        if self.rect.centery < 0:
            now_in_water = False
            self.time_since_in_air = 0

        self.time_since_in_air += 1
        if self.time_since_in_air > 1000:
            self.time_since_in_air = 1000

        # when entering water
        if now_in_water and not self.in_water:
            self.manager.get("ocean").splash(self.rect.centerx, lerp(0, 10, min(abs(self.velocity.y), 30) / 30))
            if abs(self.velocity.y) > 10:
                self.splash_sound.play()
            elif abs(self.velocity.y) > 2:
                self.small_splash_sound.play()
        
        # when exiting water
        if not now_in_water and self.in_water:
            self.manager.get("ocean").splash(self.rect.centerx, lerp(0, -10, min(abs(self.velocity.y), 30) / 30))

        # apply gravity
        if not now_in_water:
            self.velocity.y += 0.7
        else:
            # apply drag only in water
            self.velocity *= 0.95

        # remove small values of velocity
        if self.velocity.magnitude() < 0.1:
            self.velocity = pygame.Vector2(0, 0)

        # look towards
        if self.velocity.magnitude() != 0:
            self.direction = math.atan2(self.velocity.y, self.velocity.x)

        image_used = self.animation_frames[self.current_index]
        if self.direction > HALF_PI or self.direction < -HALF_PI:
            image_used = pygame.transform.flip(image_used, False, True)

        self.image = pygame.transform.rotate(image_used, -math.degrees(self.direction))
        self.rect = self.image.get_frect(center = self.rect.center)

        self.rect.center += self.velocity
        self.ammend_collisions(self.rect)
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

    def update(self):
        force = -self.extension * self.spring_constant - self.velocity * self.dampening
        self.velocity += force
        self.extension += self.velocity

class Card(Sprite):
    def __init__(self, manager: ObjectManager, position: Vec2, suit: int, value: int):
        super().__init__(manager)
        self.image = self.manager.get("card-factory").get_image(suit, value)
        self.rect = self.image.get_rect(center = position)
        self.suit = suit
        self.value = value

        self.player = self.manager.get("player")

    def update(self):
        if self.rect.colliderect(self.player.rect):
            self.kill()

class CardFactory:
    def __init__(self, manager: ObjectManager):
        self.manager = manager

        self.suits = []
        self.cards = []

        self.value_to_string = [None, "A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        self.font = pygame.font.SysFont("Trebuchet MS", 16, bold = True)

        self.suits.append(pygame.image.load("assets/fimonsh.png").convert_alpha())
        self.suits.append(pygame.image.load("assets/fearsh.png").convert_alpha())
        self.suits.append(pygame.image.load("assets/floversh.png").convert_alpha())
        self.suits.append(pygame.image.load("assets/fladesh.png").convert_alpha())

        for i in range(52):
            self.cards.append(self.create_card_image(i // 13, i % 13 + 1))

    def create_card_image(self, suit: int, value: int) -> pygame.Surface:
        surf = pygame.Surface((50, 72), pygame.SRCALPHA)
        rect = surf.get_rect()
        pygame.draw.rect(surf, (255, 255, 255), rect, border_radius = 4)
        pygame.draw.rect(surf, (200, 200, 200), rect, width = 2, border_radius = 4)

        text_colour = (166, 16, 5) if suit < 2 else (13, 38, 68)

        text = self.font.render(self.value_to_string[value], True, text_colour)
        text_rect = text.get_rect(center = (10, 8))

        icon = pygame.transform.smoothscale_by(self.suits[suit], 0.5)
        little_icon = pygame.transform.smoothscale_by(self.suits[suit], 0.17)
        
        surf.blit(icon, icon.get_rect(centerx = rect.centerx, centery = rect.centery + 10))
        surf.blit(little_icon, little_icon.get_rect(centery = 10, centerx = 40))
        surf.blit(text, text_rect)

        return surf
    
    def get_image(self, suit, value) -> pygame.Surface:
        return self.cards[suit * 13 + value - 1]

class Ocean(Sprite):
    def __init__(self, manager, layer_height: int):
        super().__init__(manager, ["update"])
        self.id = "ocean"
        self.z_index = -10

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

    def remove_spring(self, position: int):
        spring = self.springs[position]
        spring.kill()
        del self.springs[position]

    def add_more_springs(self):
        left_most_point = min(self.springs.keys())
        right_most_point = max(self.springs.keys())

        while left_most_point > self.player.rect.centerx - SCREEN_SIZE.x:
            pos = left_most_point - self.wave_interval
            self.add_spring(pos)
            left_most_point = pos

        while left_most_point < self.player.rect.centerx - SCREEN_SIZE.x:
            self.remove_spring(left_most_point)
            left_most_point += self.wave_interval
        
        while right_most_point < self.player.rect.centerx + SCREEN_SIZE.x:
            pos = right_most_point + self.wave_interval
            self.add_spring(pos)
            right_most_point = pos

        while right_most_point > self.player.rect.centerx + SCREEN_SIZE.x:
            self.remove_spring(right_most_point)
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
        surface.fill(self.colour, covered_rect)

        self.draw_waves(surface)

T = TypeVar("T", bound = Sprite)
class ObjectManager:
    def __init__(self):
        self.objects = {}
        self.render_group = pygame.sprite.Group()
        self.update_group = pygame.sprite.Group()
        self.collide_group = pygame.sprite.Group()
        self.enemy_group = pygame.sprite.Group()

    def get(self, key: str):
        return self.objects[key]
    
    def add(self, sprite: T) -> T:
        if sprite.id != "":
            self.objects[sprite.id] = sprite
        
        if "render" in sprite.group_keys:
            self.render_group.add(sprite)
        if "update" in sprite.group_keys:
            self.update_group.add(sprite)
        if "collide" in sprite.group_keys:
            self.collide_group.add(sprite)
        if "enemy" in sprite.group_keys:
            self.enemy_group.add(sprite)

        return sprite
    
    def add_obj(self, obj, key):
        self.objects[key] = obj
        return obj

class WallLeft(Sprite):
    def __init__(self, manager: ObjectManager):
        super().__init__(manager, groups = ["render"])
        self.id = "left-wall"

        self.image = pygame.Surface((SCREEN_SIZE.x, WORLD_BOTTOM + SCREEN_SIZE.y), pygame.SRCALPHA)
        self.rect = self.image.get_rect(top = 0, right = 0)
        self.image.fill(COLOUR_BORDER)

        beach = pygame.Surface((SCREEN_SIZE.x, SCREEN_SIZE.y))
        draw_gradient(beach, COLOUR_BEACH, COLOUR_BORDER)

        self.image.blit(beach, (0, 0))

        beach_mask = pygame.Surface(self.image.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(beach_mask, (255, 255, 255), [(0, 0), (self.image.get_width(), 0), (self.image.get_width(), 64)])
        beach_mask = pygame.mask.from_surface(beach_mask)
        self.image = beach_mask.to_surface(unsetsurface = self.image, setcolor = None)

class WallRight(Sprite):
    def __init__(self, manager: ObjectManager):
        super().__init__(manager, ["render"])
        self.id = "right-wall"
        border_tile = pygame.image.load("assets/border.png").convert_alpha()
        extra_stuff = 1024
        self.image = pygame.Surface((border_tile.get_width(), WORLD_BOTTOM + extra_stuff), pygame.SRCALPHA)
        for i in range(0, self.image.get_height(), border_tile.get_height()):
            self.image.blit(border_tile, (0, i))
        self.rect = self.image.get_rect(left = WORLD_RIGHT, top = -extra_stuff)

class Floor(Sprite):
    def __init__(self, manager: ObjectManager):
        super().__init__(manager, groups = ["render"])
        self.id = "floor"

        self.image = pygame.Surface((WORLD_RIGHT - WORLD_LEFT + LAYER_HEIGHT * 2, SCREEN_SIZE.y))
        self.rect = self.image.get_rect(top = LAYER_HEIGHT * 5, left = 0)
        self.image.fill(COLOUR_BORDER)

class FishLevel:
    def __init__(self, game):
        self.game = game
        self.manager = ObjectManager()
        self.manager.add_obj(game, "game")
        self.manager.add_obj(self, "level")

        self.manager.add_obj(CardFactory(self.manager), "card-factory")

        self.wall_left = self.manager.add(WallLeft(self.manager))
        self.wall_right = self.manager.add(WallRight(self.manager))
        self.floor = self.manager.add(Floor(self.manager))
        self.player = self.manager.add(Player(self.manager, (20, -20)))
        self.camera = self.manager.add(Camera(self.manager, self.player))
        self.background = self.manager.add(Ocean(self.manager, LAYER_HEIGHT))

        self.debug_mode = False
        self.debug_font = pygame.font.SysFont("Trebuchet MS", 20, False)
        self.add_cards()

    def add_cards(self, n: int = 52):
        for i in range(n):
            suit = i // 13
            value = i % 13 + 1
            # pos = (random.randrange(WORLD_LEFT + 50, WORLD_RIGHT - 50), random.randrange(-500, WORLD_BOTTOM))
            pos = (suit * 200), value * 200
            self.manager.add(Card(self.manager, pos, suit, value))

    def on_key_down(self, key: int):
        if key == pygame.K_F3:
            self.debug_mode = not self.debug_mode

    def draw_debug(self, surface: pygame.Surface):
        fps_text = self.manager.get("game").clock.get_fps()
        fps_surf = self.debug_font.render(f"{round(fps_text)} fps", True, (255, 255, 255))
        surface.blit(fps_surf, (0, 0))

        for x, spring in self.background.springs.items():
            pygame.draw.circle(surface, (0, 0, 0), self.camera.world_to_screen((x, spring.origin + spring.extension)), 2)

        for object in self.manager.render_group:
            pygame.draw.rect(surface, (0, 0, 255), (*self.camera.world_to_screen(object.rect.topleft), *object.rect.size), width = 1)

    def update(self):
        self.manager.update_group.update()

    def render(self, surface: pygame.Surface):
        surface.fill((197, 240, 251))
        self.background.render(surface)
        self.camera.render(surface, self.manager.render_group)
        if self.debug_mode:
            self.draw_debug(surface)

class Game:
    def __init__(self):
        self.window = pygame.display.set_mode(SCREEN_SIZE)
        self.clock = pygame.time.Clock()

        pygame.display.set_caption("Fish Goes Fish Go Fish Fishing")
        pygame.display.set_icon(pygame.image.load("assets/icon.png"))

        self.level = FishLevel(self)
        self.running = True

    def run(self):
        while self.running:
            self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if event.type == pygame.KEYDOWN:
                    self.level.on_key_down(event.key)

            self.window.fill((0, 0, 0))

            self.level.update()
            self.level.render(self.window)

            pygame.display.update()

        pygame.quit()

if __name__ == "__main__":
    Game().run()
