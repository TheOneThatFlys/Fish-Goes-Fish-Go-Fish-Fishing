from __future__ import annotations

import math, time, os, random
import pygame
from typing import TypeVar, Literal, get_args

import pygame.gfxdraw

pygame.init()

Vec2 = tuple[float, float]
Colour = tuple[int, int, int]
Group = Literal["render", "update", "card", "fish", "gui"]
Axis = Literal["x", "y"]

SCREEN_SIZE = pygame.Vector2(1280, 720)
FPS = 60
LAYER_HEIGHT = SCREEN_SIZE.y * 2
HALF_PI = math.pi / 2
TWO_PI = math.pi * 2
ANIMATION_TIME = 10

WORLD_LEFT = 0
WORLD_RIGHT = LAYER_HEIGHT * 10
WORLD_BOTTOM = LAYER_HEIGHT * 5

COLOUR_BEACH = (193, 149, 75)
COLOUR_BORDER = (154, 110, 39)

FISH_SIM_CENTER = 0.0003
FISH_SIM_AVOID = 0.005
FISH_SIM_MATCH_VEL = 0.04
FISH_SIM_TURN_FACTOR = 0.5
FISH_SIM_AVOID_DIST_SQUARED = 35 * 35

FISH_SIM_VISION_SQUARED = 500 * 500

def lerp(start: float, end: float, a: float):
    return (1 - a) * start + a * end

def lerp_colour(start: Colour, end: Colour, a: float):
    return (lerp(start[0], end[0], a), lerp(start[1], end[1], a), lerp(start[2], end[2], a))

def vector_from_polar(angle: float, magnitude: float) -> pygame.Vector2:
    return pygame.Vector2(math.cos(angle) * magnitude, math.sin(angle) * magnitude)

def clamp(value: float, min: float, max: float):
    if value < min:
        return min
    if value > max:
        return max
    return value

def move_towards_angle(direction_to_move: float, target_direction: float, max_turn: float) -> float:
    delta = (((target_direction - direction_to_move) + math.pi) % TWO_PI) - math.pi
    delta = clamp(delta, -max_turn, max_turn)
    return direction_to_move + delta

def draw_gradient(surface: pygame.Surface, start_colour: Colour, end_colour: Colour) -> pygame.Surface:
    """Draw vertical gradient onto surface. Modifies original surface."""
    width, height = surface.get_size()
    for i in range(height):
        t = i / height
        colour = lerp_colour(start_colour, end_colour, t)

        pygame.draw.line(surface, colour, (0, i), (width, i))
    return surface

T = TypeVar("T", bound = "Sprite")
class Manager:
    def __init__(self):
        self.objects = {}
        self.groups: dict[Group, pygame.sprite.Group] = {}
        for string in get_args(Group):
            self.groups[string] = pygame.sprite.Group()

        self.images = {}
        self.sounds = {}

    def load(self, path_to_assets: str):
        for root, dirnames, filenames in os.walk(path_to_assets):
            for filename in filenames:
                full_path = os.path.join(root, filename)
                if filename.endswith(".png"):
                    self.images[filename.removesuffix(".png")] = pygame.image.load(full_path).convert_alpha()

                elif filename.endswith(".mp3"):
                    self.sounds[filename.removesuffix(".mp3")] = pygame.mixer.Sound(full_path)

    def get_image(self, key: str) -> pygame.Surface:
        return self.images[key]
    
    def get_sound(self, key: str) -> pygame.mixer.Sound:
        return self.sounds[key]
    
    def play_sound(self, key: str, relative_volume: float = 1):
        s = self.get_sound(key)
        s.set_volume(relative_volume)
        s.play()

    def get(self, key: str):
        return self.objects[key]
    
    def add(self, sprite: T) -> T:
        if sprite.id != "":
            self.objects[sprite.id] = sprite

        for key, group in self.groups.items():
            if key in sprite.group_keys:
                group.add(sprite)

        return sprite
    
    def add_obj(self, obj, key):
        self.objects[key] = obj
        return obj

class Sprite(pygame.sprite.Sprite):
    def __init__(self, manager: Manager, groups: list[Group] = ["render", "update"]):
        super().__init__()
        self.manager = manager
        self.group_keys = groups
        self.id = ""
        self.z_index = 0

class TextBox(Sprite):
    def __init__(self, manager: Manager, text: str, font_size: int = 20, colour: Colour = (255, 255, 255), **rect_args):
        super().__init__(manager, groups = ["gui", "update"])
        self.font = pygame.font.SysFont("Trebuchet MS", font_size)
        self.text = text
        self.font_size = font_size
        self.colour = colour
        self.rect_args =  rect_args

        self.set_text(text)

    def set_text(self, text: str):
        self.text = text
        self.image = self.font.render(text, True, self.colour)
        self.rect = self.image.get_rect(**self.rect_args)

    def update(self):
        pass

class Player(Sprite):
    def __init__(self, manager: Manager, initial_velocity: Vec2 = (0, 0)):
        super().__init__(manager)
        self.id = "player"
        self.z_index = 1
        
        self.original_animation_frames: list[pygame.Surface] = []
        self.current_index = 0
        self.animation_counter = 0
        for i in range(2):
            self.original_animation_frames.append(pygame.transform.scale_by(self.manager.get_image(f"swordfish_{i}"), 0.25))

        self.card_collected_image = pygame.transform.smoothscale_by(self.manager.get_image("card_nose"), 0.25)
        self.animation_frames = [image.copy() for image in self.original_animation_frames]
        self.collected_card_offsets: list[int] = []

        self.image = self.animation_frames[0]
        self.rect = self.image.get_frect(bottom = self.manager.get("left-wall").rect.top, left = 0)
        self.direction = 0

        self.speed = 1.5

        self.velocity = pygame.Vector2(initial_velocity)

        self.in_water = self.rect.centery > 0
        self.time_since_in_air = 0 if self.in_water else 100

    def collect_card(self):
        if self.collected_card_offsets:
            self.collected_card_offsets.append(random.randint(-4, 4))
        else:
            # make sure first card is always no offset
            self.collected_card_offsets.append(0)

        rects = []
        for x, offset in enumerate(self.collected_card_offsets):
            r = self.card_collected_image.get_rect(centery = 43 + offset, x = 165 + x)
            rects.append(r)

        rects.reverse()

        for i, frame in enumerate(self.original_animation_frames):
            new_image = frame.copy()
            for r in rects:
                new_image.blit(self.card_collected_image, r)

            self.animation_frames[i] = new_image

    def calculate_nose_hitbox(self):
        self.nose_hitbox = pygame.Rect(0, 0, 1, 1)

        mid_point = pygame.Vector2(self.rect.center)
        base_offset = vector_from_polar(self.direction, 50)
        point_offset = vector_from_polar(self.direction, 120)

        p1 = base_offset + mid_point
        p2 = point_offset + mid_point

        topleft = pygame.Vector2(min(p1.x, p2.x), min(p1.y, p2.y))
        bottom_right = pygame.Vector2(max(p1.x, p2.x), max(p1.y, p2.y))

        self.nose_hitbox.width = max(bottom_right.x - topleft.x, 1)
        self.nose_hitbox.height = max(bottom_right.y - topleft.y, 1)
        self.nose_hitbox.topleft = topleft

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
            if abs(self.velocity.y) > 7:
                self.manager.play_sound("splash", 0.3)
        
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
        self.calculate_nose_hitbox()
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
    def __init__(self, manager: Manager, position: Vec2, suit: int, value: int):
        super().__init__(manager, groups = ["render", "update", "card"])
        self.image = self.manager.get("card-factory").get_image(suit, value)
        self.rect = self.image.get_rect(center = position)
        self.suit = suit
        self.value = value

        self.player: Player = self.manager.get("player")

        self.origin = self.rect.centery
        self.max_offset = 20
        self.timer = random.random() * math.pi * 2

    def update(self):
        self.timer += 0.1
        if self.timer > math.pi * 2:
            self.timer = 0
        self.rect.centery = self.origin + math.sin(self.timer) * self.max_offset

        if self.rect.colliderect(self.player.nose_hitbox):
            self.kill()

    def kill(self):
        self.manager.play_sound("pickup", 0.8)
        self.manager.get("card-display").collect_card(self.suit, self.value)
        self.manager.get("player").collect_card()
        super().kill()

class CardFactory:
    def __init__(self, manager: Manager):
        self.manager = manager

        self.suits = []
        self.cards = []

        self.value_to_string = [None, "A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        self.font = pygame.font.SysFont("Trebuchet MS", 16, bold = True)

        fishes = ["fimonsh", "fearsh", "floversh", "fladesh"]
        for fish in fishes:
            self.suits.append(self.manager.get_image(fish))

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
    
    def get_image(self, suit: int, value: int) -> pygame.Surface:
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

class WallLeft(Sprite):
    def __init__(self, manager: Manager):
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
    def __init__(self, manager: Manager):
        super().__init__(manager, ["render"])
        self.id = "right-wall"
        border_tile = self.manager.get_image("border")
        extra_stuff = 1024
        self.image = pygame.Surface((border_tile.get_width(), WORLD_BOTTOM + extra_stuff), pygame.SRCALPHA)
        for i in range(0, self.image.get_height(), border_tile.get_height()):
            self.image.blit(border_tile, (0, i))
        self.rect = self.image.get_rect(left = WORLD_RIGHT, top = -extra_stuff)

class Floor(Sprite):
    def __init__(self, manager: Manager):
        super().__init__(manager, groups = ["render"])
        self.id = "floor"

        self.image = pygame.Surface((WORLD_RIGHT - WORLD_LEFT + LAYER_HEIGHT * 2, SCREEN_SIZE.y))
        self.rect = self.image.get_rect(top = LAYER_HEIGHT * 5, left = 0)
        self.image.fill(COLOUR_BORDER)

class FishBoid(Sprite):
    def __init__(self, manager: Manager, position: Vec2, direction: float, image: pygame.Surface, boid_group: pygame.sprite.Group, bounds: pygame.Rect):
        super().__init__(manager, ["render"])
        self.original_image = image
        self.rect = image.get_frect(center = position)

        self.speed_limit = 10
        self.velocity: pygame.Vector2 = vector_from_polar(direction, self.speed_limit)

        self.boid_group = boid_group
        self.bounds = bounds

    def go_towards_center(self, boids: list[FishBoid]):
        num_boids = 0
        avg_pos = pygame.Vector2()
        for boid in boids:
            avg_pos += boid.rect.center
            num_boids += 1

        if num_boids:
            avg_pos = avg_pos / num_boids
            self.velocity += (avg_pos - self.rect.center) * FISH_SIM_CENTER
    
    def avoid_others(self, boids: list[FishBoid]):
        dv = pygame.Vector2()
        for boid in boids:
            if boid == self: continue
            if (pygame.Vector2(boid.rect.center) - self.rect.center).magnitude_squared() < FISH_SIM_AVOID_DIST_SQUARED:
                dv += self.rect.center - pygame.Vector2(boid.rect.center)

        self.velocity += dv * FISH_SIM_AVOID

    def match_velocity(self, boids: list[FishBoid]):
        num_boids = 0
        avg_vel = pygame.Vector2()
        for boid in boids:
            avg_vel += boid.velocity
            num_boids += 1

        if num_boids:
            avg_vel = avg_vel / num_boids
            self.velocity += (avg_vel - self.velocity) * FISH_SIM_MATCH_VEL

    def keep_within_bounds(self):
        if self.rect.x < self.bounds.x:
            self.velocity.x += FISH_SIM_TURN_FACTOR
        if self.rect.right > self.bounds.right:
            self.velocity.x -= FISH_SIM_TURN_FACTOR
        if self.rect.y < self.bounds.y:
            self.velocity.y += FISH_SIM_TURN_FACTOR
        if self.rect.bottom > self.bounds.bottom:
            self.velocity.y -= FISH_SIM_TURN_FACTOR

    def update(self, boids: list[FishBoid]):
        self.go_towards_center(boids)
        self.avoid_others(boids)
        self.match_velocity(boids)

        self.velocity.clamp_magnitude_ip(self.speed_limit)

        self.keep_within_bounds()

        self.rect.topleft += self.velocity
        direction = math.atan2(self.velocity.y, self.velocity.x)
        self.image = pygame.transform.rotate(self.original_image, -math.degrees(direction))

class BoidManager(Sprite):
    def __init__(self, manager: Manager, num_fish_per_group: int = 50):
        super().__init__(manager, ["update"])
        self.id = "boid-manager"

        self.fish_groups = [pygame.sprite.Group() for _ in range(4)]
        self.bounding_rect = pygame.Rect(WORLD_LEFT + 10, 100, WORLD_RIGHT - WORLD_LEFT - 10, WORLD_BOTTOM - 110)

        self.create_boids(num_fish_per_group)

    def create_boids(self, num_fish_per_group: int):
        fish_names = ["fimonsh", "fearsh", "floversh", "fladesh"]
        for i, group in enumerate(self.fish_groups):
            
            img = self.manager.get_image(fish_names[i])
            img = pygame.transform.rotate(img, -90)
            img = pygame.transform.smoothscale_by(img, 0.5)

            for _ in range(num_fish_per_group):
                random_pos = (random.randint(self.bounding_rect.x, self.bounding_rect.right), random.randint(self.bounding_rect.y, self.bounding_rect.bottom))
                fish = FishBoid(self.manager, random_pos, random.random() * math.pi * 2 - math.pi, img, group, self.bounding_rect)
                self.manager.add(fish)
                group.add(fish)

    def update(self):
        for fish_suit in self.fish_groups:
            for boid in fish_suit.sprites():
                boids = [b for b in fish_suit.sprites() if (pygame.Vector2(b.rect.center) - boid.rect.center).magnitude_squared() < FISH_SIM_VISION_SQUARED]
                boid.update(boids)

class Compass(Sprite):
    def __init__(self, manager: Manager):
        super().__init__(manager, ["update", "gui"])
        self.size = (128, 128)
        self.direction = 0

        self.player: Player = self.manager.get("player")

        self.bg = self.render_background()
        self.draw_image()

    def render_background(self) -> pygame.Surface:
        surf = pygame.Surface(self.size, pygame.SRCALPHA)
        rect = surf.get_rect(bottomright = (SCREEN_SIZE - (8, 8)))

        radius = rect.width / 2 - 1

        pygame.gfxdraw.circle(surf, int(radius), int(radius), int(radius), (255, 255, 255))
        pygame.gfxdraw.circle(surf, int(radius), int(radius), int(radius - 1), (255, 255, 255))

        steps = 60
        increment = math.pi * 2 / steps
        for i in range(steps):
            angle = increment * i
            width = 2 if i % (steps / 4) == 0 else 1
            line_size = 12 if i % (steps / 4) == 0 else 6

            start = (radius, radius) + vector_from_polar(angle, radius - 1)
            end = (radius, radius) + vector_from_polar(angle, radius - line_size)

            pygame.draw.line(surf, (255, 255, 255), start, end, width)
        return surf

    def get_closest_card_direction(self) -> float:
        def __distance_to_player(sprite):
            return (pygame.Vector2(sprite.rect.centerx, sprite.origin) - self.player.rect.center).magnitude()
        
        if len(self.manager.groups["card"]) == 0: return 0

        closest_card = min(self.manager.groups["card"], key = __distance_to_player)
        dv = pygame.Vector2(closest_card.rect.centerx, closest_card.origin) - self.player.rect.center
        direction = math.atan2(dv.y, dv.x)

        return direction

    def draw_image(self):
        self.image = pygame.Surface(self.size, pygame.SRCALPHA)
        self.rect = self.image.get_rect(bottomright = (SCREEN_SIZE - (8, 8)))
        self.image.blit(self.bg, (0, 0))

        if len(self.manager.groups["card"]) == 0:
            direction_to_card = self.direction + 0.05
        else:
            direction_to_card = self.get_closest_card_direction()

        self.direction = move_towards_angle(self.direction, direction_to_card, 0.1)

        COMPASS_THICKNESS = 4
        radius = self.size[0] / 2
        left_base = (radius, radius) + vector_from_polar(self.direction + math.pi / 2, COMPASS_THICKNESS)
        right_base = (radius, radius) + vector_from_polar(self.direction - math.pi / 2, COMPASS_THICKNESS)
        end_pos = pygame.Vector2(radius, radius) + vector_from_polar(self.direction, 40)

        pygame.gfxdraw.aapolygon(self.image, [left_base, right_base, end_pos], (255, 0, 0))
        pygame.gfxdraw.filled_polygon(self.image, [left_base, right_base, end_pos], (255, 0, 0))

    def update(self):
        self.draw_image()

class CardDisplay(Sprite):
    def __init__(self, manager: Manager):
        super().__init__(manager, ["update", "gui"])
        self.id = "card-display"

        # suit num points to index, contains list of values collected
        self.collected_cards: list[list[int]] = [[], [], [], []]

        self.card_size = (25, 36)
        self.vertical_padding = 10
        self.horizontal_padding = 8

        self.card_factory: CardFactory = self.manager.get("card-factory")

        self.draw_image()

    def collect_card(self, suit: int, value: int):
        self.collected_cards[suit].append(value)

    def draw_image(self):
        self.image = pygame.Surface((self.card_size[0] * 13 + self.horizontal_padding * 12, self.card_size[1] + 3 * self.vertical_padding), pygame.SRCALPHA)
        self.rect = self.image.get_rect(bottom = SCREEN_SIZE.y - 8, x = 8)

        for suit, cards in enumerate(self.collected_cards):
            for value in range(1, 14):
                if value in cards:
                    card_image = pygame.transform.smoothscale(self.card_factory.get_image(suit, value), self.card_size)
                else:
                    card_image = pygame.Surface(self.card_size, pygame.SRCALPHA)
                    temp_rect = card_image.get_rect()
                    pygame.draw.rect(card_image, (28, 30, 37), temp_rect, border_radius = 4)
                    pygame.draw.rect(card_image, (18, 20, 27), temp_rect, width = 2, border_radius = 4)
                
                pos = (
                    (value - 1) * (self.card_size[0] + self.horizontal_padding),
                    self.vertical_padding * suit
                )

                self.image.blit(card_image, pos)

        for value in range(1, 14):
            collected_suit = True
            for cards in self.collected_cards:
                if value not in cards:
                    collected_suit = False
                    break
            if not collected_suit: continue

            position = (value - 1) * (self.card_size[0] + self.horizontal_padding), 0
            rect = pygame.Rect(*position, self.card_size[0], self.card_size[1] + 3 * self.vertical_padding)

            pygame.draw.rect(self.image, (255, 215, 0), rect, width = 1, border_radius = 4)

    def update(self):
        self.draw_image()

class Timer(TextBox):
    def __init__(self, manager: Manager):
        super().__init__(manager, "0.00", 20, (255, 255, 255), centerx = SCREEN_SIZE.x / 2, top = 8)
        self.start_time = time.time()
        self.finished = False

    def update(self):
        if not self.finished:
            new_time = time.time()
            self.set_text(f"{round(new_time - self.start_time, 2)}s")

            if len(self.manager.groups["card"]) == 0:
                self.finished = True
                self.colour = (255, 215, 0)
                self.set_text(self.text)

class FishLevel:
    def __init__(self, game):
        self.game = game
        self.manager = Manager()
        self.manager.load(os.path.join(os.path.curdir, "assets"))
        self.manager.add_obj(game, "game")
        self.manager.add_obj(self, "level")

        self.manager.add_obj(CardFactory(self.manager), "card-factory")

        self.wall_left = self.manager.add(WallLeft(self.manager))
        self.wall_right = self.manager.add(WallRight(self.manager))
        self.floor = self.manager.add(Floor(self.manager))

        self.player = self.manager.add(Player(self.manager, (20, -20)))
        self.camera = self.manager.add(Camera(self.manager, self.player))
        self.background = self.manager.add(Ocean(self.manager, LAYER_HEIGHT))

        self.boid_manager = self.manager.add(BoidManager(self.manager))

        self.compass = self.manager.add(Compass(self.manager))
        self.card_display = self.manager.add(CardDisplay(self.manager))
        self.timer = self.manager.add(Timer(self.manager))

        self.debug_mode = False
        self.debug_font = pygame.font.SysFont("Trebuchet MS", 20, False)
        self.add_cards()

    def add_cards(self, n: int = 52):
        for i in range(n):
            suit = i // 13
            value = i % 13 + 1
            pos = (random.randint(WORLD_LEFT + 100, WORLD_RIGHT - 100), random.randint(-500, WORLD_BOTTOM - 100))
            # pos = (suit * 200), value * 200
            self.manager.add(Card(self.manager, pos, suit, value))

    def on_key_down(self, key: int):
        if key == pygame.K_F3:
            self.debug_mode = not self.debug_mode
        if key == pygame.K_p:
            for card in self.manager.groups["card"].sprites():
                card.kill()

    def draw_debug(self, surface: pygame.Surface):
        fps = self.manager.get("game").clock.get_fps()
        fps_surf = self.debug_font.render(f"{round(fps)} fps", True, (255, 255, 255))
        fps_rect = fps_surf.get_rect()
        surface.blit(fps_surf, (0, 0))

        pos_surf = self.debug_font.render(f"{self.player.rect.centerx}, {self.player.rect.centery}", True, (255, 255, 255))
        pos_rect = pos_surf.get_rect(top = fps_rect.bottom)
        surface.blit(pos_surf, pos_rect)

        for x, spring in self.background.springs.items():
            pygame.draw.circle(surface, (0, 0, 0), self.camera.world_to_screen((x, spring.origin + spring.extension)), 2)

        for object in self.manager.groups["render"]:
            pygame.draw.rect(surface, (0, 0, 255), (*self.camera.world_to_screen(object.rect.topleft), *object.rect.size), width = 1)

        pygame.draw.rect(surface, (255, 0, 0), (*self.camera.world_to_screen(self.player.nose_hitbox.topleft), *self.player.nose_hitbox.size), width = 1)

    def update(self):
        self.manager.groups["update"].update()

    def render(self, surface: pygame.Surface):
        surface.fill((197, 240, 251))
        self.background.render(surface)
        self.camera.render(surface, self.manager.groups["render"])

        for sprite in self.manager.groups["gui"].sprites():
            surface.blit(sprite.image, sprite.rect)

        if self.debug_mode:
            self.draw_debug(surface)

class Camera(Sprite):
    def __init__(self, manager: Manager, target: Sprite):
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

class Game:
    def __init__(self):
        self.window = pygame.display.set_mode(SCREEN_SIZE)
        self.clock = pygame.time.Clock()

        pygame.display.set_caption("Fish Goes Fish Go Fish Fishing")
        pygame.display.set_icon(pygame.image.load("assets/icon.png").convert())

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