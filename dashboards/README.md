# Дашборд района — исходники (без приватных данных)

В репо **нет** самого дашборда и реальных камер (entity/замки/названия —
приватные). Всё генерируется из `cameras.json` (gitignored):

```bash
cp dashboards/cameras.example.json dashboards/cameras.json
$EDITOR dashboards/cameras.json
```

## Карточка: `custom:district-intercom-card`

Дашборд собирается из карточек `custom:district-intercom-card` (JS лежит в
интеграции; при setup она синхронизирует его в `<config>/www/district/`,
Lovelace-ресурс `/local/district/district-intercom-card.js?v=<version>`
регистрирует `install.sh` — однократно, идемпотентно).

Конфиг карточки (замороженный контракт):

```yaml
type: custom:district-intercom-card
entity: lock.front_gate               # lock-энтити двери; omitted = camera-only
views:                                # явный список camera entities
  - camera.front_gate_wide
  - camera.front_gate_closeup
image: /local/snapshots/front-gate-wide.jpg  # опц. обложка; дефолт placeholder
snapshot_file: front-gate-wide.jpg    # опц. цель refresh; дефолт по первому view
title: Front Gate                     # опц.
open_text: Open                       # опц., дефолт "Open"
```

Поведение: обложка = `image`/placeholder; кнопка refresh сверху справа
(`hikcentral_district.refresh_snapshot` → обложка); кнопка Open снизу во всю
ширину (`lock.open`, скрыта без `entity`); клик по карточке → popup
(browser_mod) со стримом активного view + колонка кнопок views справа.
Пустые `views` при наличии `entity` = Open-only карточка.

## Схема cameras.json

```jsonc
{
  "dashboard": {                 // мета дашборда
    "title": "...",              // заголовок дашборда
    "view_title": "...",         // заголовок вью/heading-карточки
    "url_path": "district"       // URL: /<url_path>
  },
  "cameras": [
    {
      "id": "111",                          // id камеры в HikCentral
      "entity": "camera.front_gate_wide",   // camera-энтити HA
      "lock": "lock.front_gate",            // lock-энтити двери ИЛИ null
      "jpg": "/local/snapshots/....jpg",    // снапшот-обложка (www/snapshots/)
      "title": "Front Gate",                // название
      "codec": "h264"                       // h264|h265 (для go2rtc-конфига)
    }
  ],
  "locks_only": [                // опц.: двери без камер (Open-only карточки)
    {"lock": "lock.back_door", "title": "Back Door"}
  ]
}
```

### Группировка по замку → views

- Камеры с **одним `lock`** собираются в **одну карточку на дверь**:
  `views` = их `entity` в порядке файла, `entity` = общий lock,
  `image`/`snapshot_file` = jpg **первой** камеры, `title` = title первой
  камеры.
- Камеры с **`lock: null`** — отдельные **camera-only** карточки
  (`views: [<entity>]`, без Open-кнопки).
- **`locks_only`** (опциональный массив) — **Open-only** карточки для дверей
  без стримируемых камер: `entity` = lock, `views: []`. Ключ отсутствует —
  таких карточек нет (обратная совместимость).

## Генераторы

```bash
# дашборд: скелет с нуля (так делает install.sh)
python3 dashboards/generate_district.py --create lovelace.district.json

# дашборд: пересборка карточек в существующем экспорте — идемпотентно;
# старые v7-пары picture-glance + custom:popup-card заменяются новыми
# карточками, дубликаты схлопываются, прочие карточки не трогаются
python3 dashboards/generate_district.py --check lovelace.district.json

# go2rtc-hik sidecar конфиг (h264 прямые, h265 через ffmpeg#video=h264)
python3 deploy/generate_go2rtc.py go2rtc.yaml
```

Грабли, зашитые в go2rtc-генератор: источники go2rtc — однострочные квоченные
строки; никакого `#audio=none`; HEVC-камерам нужен `_src` + обёртка;
go2rtc exec ждёт сырой Annex-B, стартующий с SPS/VPS (мост делает сам).


### Автодискавер домофон-каналов (autodiscover.py)

На серверах HikCentral Professional < V3 (проверено на V1.7) мобильное
приложение показывает у интеркома ТОЛЬКО канал вызывной панели — серверных
CCTV-связок (`RelatedElementList`) там не существует. Единственная
«правильная по серверу» камера двери — её домофонный канал.

`autodiscover.py` находит его для каждой двери из карты `"doors"` в
cameras.json (lock entity → door id) и ставит первым view группы, не
трогая ваши CCTV-надстройки. Идемпотент; правки entity/названий после
дискавера сохраняются (сверка по id камеры).

```bash
HIK_URL=... HIK_USER=... HIK_PASS=... \
  python3 dashboards/autodiscover.py --write        # dry-run без --write
```

door id = суффикс unique_id замка в HA
(`hikcentral_district.lock.<id>`); entity камеры выводится той же
slugify-нормализацией, что использует HA (проверено на живых id).

## Применение (наш прод)

Живой дашборд — источник правды в приватном мега-репо
`platform/homeassistant/dashboards/` (district.json там + этот же
генератор, но с уже заполненным cameras.json). Экспорт/применение:

```bash
docker exec homeassistant cp /config/.storage/lovelace.district /config/.storage/lovelace.district.bak_$(date +%Y%m%d)
docker cp district.json homeassistant:/config/.storage/lovelace.district
# рестарт стека — только через Komodo
```
