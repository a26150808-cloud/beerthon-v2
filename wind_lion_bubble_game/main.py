import math
import random
import sys
from array import array

import pygame


WIDTH = 960
HEIGHT = 640
FPS = 60
TITLE = "風獅爺戳泡泡"

PASTEL_SKY = (177, 225, 239)
PASTEL_SEA = (111, 200, 216)
PASTEL_SAND = (246, 221, 168)
WHITE = (255, 255, 255)
SOFT_BLUE = (145, 220, 239)
SOFT_PINK = (255, 190, 205)
SOFT_YELLOW = (255, 235, 142)
SOFT_GREEN = (157, 219, 176)
INK = (92, 74, 61)

CHEERS = ["太棒了！", "好厲害！", "風獅爺笑了！", "再戳一個！"]


def make_click_sound():
    sample_rate = 44100
    samples = int(sample_rate * 0.12)
    buffer = array("h")

    for i in range(samples):
        t = i / sample_rate
        envelope = max(0.0, 1.0 - i / samples)
        tone = math.sin(2 * math.pi * 880 * t) * 0.55
        sparkle = math.sin(2 * math.pi * 1320 * t) * 0.25
        value = int((tone + sparkle) * envelope * 14000)
        buffer.append(value)

    return pygame.mixer.Sound(buffer=buffer)


def get_font(size):
    names = [
        "Microsoft JhengHei",
        "Microsoft YaHei",
        "Noto Sans CJK TC",
        "PingFang TC",
        "SimHei",
    ]
    return pygame.font.SysFont(names, size, bold=True)


def draw_round_text(surface, text, font, color, center):
    shadow = font.render(text, True, (255, 255, 255))
    label = font.render(text, True, color)
    shadow_rect = shadow.get_rect(center=(center[0] + 2, center[1] + 2))
    label_rect = label.get_rect(center=center)
    surface.blit(shadow, shadow_rect)
    surface.blit(label, label_rect)


class FloatingText:
    def __init__(self, text, pos, font):
        self.text = text
        self.x, self.y = pos
        self.font = font
        self.life = 90
        self.max_life = 90

    def update(self):
        self.y -= 0.45
        self.life -= 1

    def draw(self, surface):
        alpha = max(0, min(255, int(255 * self.life / self.max_life)))
        label = self.font.render(self.text, True, (231, 99, 126))
        label.set_alpha(alpha)
        rect = label.get_rect(center=(self.x, self.y))
        surface.blit(label, rect)

    @property
    def alive(self):
        return self.life > 0


class Bubble:
    def __init__(self):
        self.respawn()

    def respawn(self):
        self.radius = random.randint(54, 78)
        self.x = random.randint(self.radius + 20, WIDTH - self.radius - 20)
        self.y = random.randint(170, HEIGHT - self.radius - 70)
        self.vx = random.uniform(-0.35, 0.35)
        self.vy = random.uniform(-0.28, 0.18)
        self.wobble = random.uniform(0, math.tau)
        self.wobble_speed = random.uniform(0.018, 0.032)
        self.color = random.choice([SOFT_BLUE, SOFT_PINK, SOFT_YELLOW, SOFT_GREEN])

    def update(self):
        self.wobble += self.wobble_speed
        self.x += self.vx + math.sin(self.wobble) * 0.18
        self.y += self.vy + math.cos(self.wobble * 0.8) * 0.12

        if self.x < self.radius + 12:
            self.x = self.radius + 12
            self.vx = abs(self.vx)
        if self.x > WIDTH - self.radius - 12:
            self.x = WIDTH - self.radius - 12
            self.vx = -abs(self.vx)
        if self.y < 140:
            self.y = 140
            self.vy = abs(self.vy) * 0.5
        if self.y > HEIGHT - self.radius - 40:
            self.y = HEIGHT - self.radius - 40
            self.vy = -abs(self.vy) * 0.5

    def contains(self, pos):
        px, py = pos
        return math.hypot(px - self.x, py - self.y) <= self.radius

    def draw(self, surface):
        cx, cy, r = int(self.x), int(self.y), self.radius

        bubble_layer = pygame.Surface((r * 2 + 16, r * 2 + 16), pygame.SRCALPHA)
        center = (r + 8, r + 8)
        pygame.draw.circle(bubble_layer, (*self.color, 118), center, r)
        pygame.draw.circle(bubble_layer, (255, 255, 255, 170), center, r, 4)
        pygame.draw.circle(bubble_layer, (255, 255, 255, 150), (center[0] - r // 3, center[1] - r // 3), r // 5)
        surface.blit(bubble_layer, (cx - r - 8, cy - r - 8))

        draw_shisa(surface, cx, cy, r)


def draw_shisa(surface, cx, cy, radius):
    scale = radius / 70
    face_w = int(72 * scale)
    face_h = int(58 * scale)
    face_rect = pygame.Rect(0, 0, face_w, face_h)
    face_rect.center = (cx, cy + int(5 * scale))

    mane_color = (243, 150, 95)
    face_color = (255, 205, 135)
    cheek_color = (255, 160, 170)
    mouth_color = (208, 91, 91)

    for angle in range(0, 360, 30):
        rad = math.radians(angle)
        px = cx + math.cos(rad) * face_w * 0.48
        py = cy + int(5 * scale) + math.sin(rad) * face_h * 0.46
        pygame.draw.circle(surface, mane_color, (int(px), int(py)), int(13 * scale))

    left_ear = [(cx - int(35 * scale), cy - int(24 * scale)), (cx - int(52 * scale), cy - int(56 * scale)), (cx - int(18 * scale), cy - int(42 * scale))]
    right_ear = [(cx + int(35 * scale), cy - int(24 * scale)), (cx + int(52 * scale), cy - int(56 * scale)), (cx + int(18 * scale), cy - int(42 * scale))]
    pygame.draw.polygon(surface, mane_color, left_ear)
    pygame.draw.polygon(surface, mane_color, right_ear)
    pygame.draw.polygon(surface, (255, 196, 137), [
        (cx - int(35 * scale), cy - int(32 * scale)),
        (cx - int(42 * scale), cy - int(47 * scale)),
        (cx - int(24 * scale), cy - int(39 * scale)),
    ])
    pygame.draw.polygon(surface, (255, 196, 137), [
        (cx + int(35 * scale), cy - int(32 * scale)),
        (cx + int(42 * scale), cy - int(47 * scale)),
        (cx + int(24 * scale), cy - int(39 * scale)),
    ])

    pygame.draw.ellipse(surface, face_color, face_rect)
    pygame.draw.ellipse(surface, INK, face_rect, max(2, int(3 * scale)))

    for ex in (-20, 20):
        eye_center = (cx + int(ex * scale), cy - int(5 * scale))
        pygame.draw.circle(surface, WHITE, eye_center, int(11 * scale))
        pygame.draw.circle(surface, INK, eye_center, int(5 * scale))
        pygame.draw.circle(surface, WHITE, (eye_center[0] - int(2 * scale), eye_center[1] - int(2 * scale)), max(1, int(2 * scale)))

    pygame.draw.circle(surface, cheek_color, (cx - int(28 * scale), cy + int(14 * scale)), int(8 * scale))
    pygame.draw.circle(surface, cheek_color, (cx + int(28 * scale), cy + int(14 * scale)), int(8 * scale))
    pygame.draw.circle(surface, INK, (cx, cy + int(6 * scale)), int(6 * scale))
    pygame.draw.arc(surface, mouth_color, (cx - int(18 * scale), cy + int(6 * scale), int(36 * scale), int(28 * scale)), 0.15, math.pi - 0.15, max(2, int(4 * scale)))

    for tx in (-16, 0, 16):
        tooth = [
            (cx + int(tx * scale), cy + int(23 * scale)),
            (cx + int((tx - 5) * scale), cy + int(34 * scale)),
            (cx + int((tx + 5) * scale), cy + int(34 * scale)),
        ]
        pygame.draw.polygon(surface, WHITE, tooth)


def draw_background(surface, frame):
    surface.fill(PASTEL_SKY)

    sun_x, sun_y = WIDTH - 120, 92
    pygame.draw.circle(surface, (255, 232, 142), (sun_x, sun_y), 48)
    pygame.draw.circle(surface, (255, 246, 187), (sun_x - 14, sun_y - 14), 18)

    for base_x in (90, 310, 590, 810):
        bob = math.sin(frame * 0.012 + base_x) * 4
        pygame.draw.ellipse(surface, (255, 255, 255), (base_x, 78 + bob, 86, 30))
        pygame.draw.ellipse(surface, (255, 255, 255), (base_x + 36, 62 + bob, 74, 42))
        pygame.draw.ellipse(surface, (255, 255, 255), (base_x + 84, 82 + bob, 76, 28))

    pygame.draw.rect(surface, PASTEL_SEA, (0, 270, WIDTH, 200))
    for y in (304, 350, 398):
        points = []
        for x in range(0, WIDTH + 20, 20):
            wave = math.sin((x * 0.025) + frame * 0.03 + y) * 8
            points.append((x, int(y + wave)))
        pygame.draw.lines(surface, (218, 250, 250), False, points, 3)

    pygame.draw.rect(surface, PASTEL_SAND, (0, 460, WIDTH, HEIGHT - 460))
    pygame.draw.arc(surface, (229, 194, 129), (-90, 430, 280, 115), 0, math.pi, 4)
    pygame.draw.arc(surface, (229, 194, 129), (690, 445, 350, 130), 0, math.pi, 4)

    for x, y, color in [
        (78, 548, SOFT_PINK),
        (156, 584, SOFT_BLUE),
        (794, 558, SOFT_GREEN),
        (868, 596, SOFT_YELLOW),
    ]:
        pygame.draw.circle(surface, color, (x, y), 10)
        pygame.draw.circle(surface, WHITE, (x - 3, y - 3), 3)


def main():
    pygame.mixer.pre_init(44100, -16, 1, 512)
    pygame.init()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()

    score_font = get_font(34)
    cheer_font = get_font(44)
    small_font = get_font(22)

    try:
        click_sound = make_click_sound()
    except pygame.error:
        click_sound = None

    bubbles = [Bubble() for _ in range(6)]
    floating_texts = []
    score = 0
    frame = 0

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                if event.type == pygame.FINGERDOWN:
                    pos = (int(event.x * WIDTH), int(event.y * HEIGHT))
                else:
                    pos = event.pos

                for bubble in sorted(bubbles, key=lambda b: b.radius, reverse=True):
                    if bubble.contains(pos):
                        score += 1
                        if click_sound:
                            click_sound.play()
                        floating_texts.append(FloatingText(random.choice(CHEERS), (bubble.x, bubble.y - bubble.radius - 10), cheer_font))
                        bubble.respawn()
                        break

        for bubble in bubbles:
            bubble.update()

        for text in floating_texts:
            text.update()
        floating_texts = [text for text in floating_texts if text.alive]

        draw_background(screen, frame)

        for bubble in bubbles:
            bubble.draw(screen)

        pygame.draw.rect(screen, (255, 250, 225), (20, 18, 286, 58), border_radius=24)
        pygame.draw.rect(screen, (239, 177, 129), (20, 18, 286, 58), width=3, border_radius=24)
        score_label = score_font.render(f"收集風獅爺：{score}", True, INK)
        screen.blit(score_label, (42, 28))

        tip = small_font.render("點一下泡泡，風獅爺會出來玩", True, (112, 93, 73))
        screen.blit(tip, (WIDTH - tip.get_width() - 24, HEIGHT - 34))

        for text in floating_texts:
            text.draw(screen)

        pygame.display.flip()
        clock.tick(FPS)
        frame += 1

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
