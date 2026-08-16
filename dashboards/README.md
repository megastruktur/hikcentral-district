# Дашборд камер — исходники (без приватных данных)

В репо **нет** самого дашборда и реальных камер (entity/замки/названия —
приватные). Всё генерируется из `cameras.json` (gitignored):

```bash
cp dashboards/cameras.example.json dashboards/cameras.json
$EDITOR dashboards/cameras.json   # твои камеры: id, entity, lock, jpg, title, codec
```

Форма карточки (v7):

- **статичная** — core `picture-glance`: снапшот-jpg + иконка 🔓
  (`lock.open`, без подтверждения); тап по картинке → **нативный more-info**
  камеры (видео играет всегда, ноль кастомных зависимостей)
- **popup-card** (browser_mod, невидима вне edit mode) — подменяет more-info
  на live-видео с плейсхолдером фиксированной высоты (`aspect_ratio: 16:9`)
  + большую кнопку «ОТКРЫТЬ». Не сработал browser_mod — остаётся нативный
  плеер (graceful degradation).

## Генераторы

```bash
# дашборд: скелет с нуля
python3 dashboards/generate_district.py --create lovelace.district.json
# дашборд: пересборка карточек в существующем экспорте (идемпотентно,
# нормализует до 1 статик + 1 popup-card на камеру)
python3 dashboards/generate_district.py --check lovelace.district.json

# go2rtc-hik sidecar конфиг (h264 прямые, h265 через ffmpeg#video=h264)
python3 deploy/generate_go2rtc.py go2rtc.yaml
```

Грабли, зашитые в генераторы: источники go2rtc — однострочные квоченные
строки; никакого `#audio=none`; HEVC-камерам нужен `_src` + обёртка;
go2rtc exec ждёт сырой Annex-B, стартующий с SPS/VPS (мост делает сам).

## Применение (наш прод)

Живой дашборд — источник правды в приватном мега-репо
`platform/homeassistant/dashboards/` (district.json там + этот же
генератор, но с уже заполненным cameras.json). Экспорт/применение:

```bash
docker exec homeassistant cp /config/.storage/lovelace.district /config/.storage/lovelace.district.bak_$(date +%Y%m%d)
docker cp district.json homeassistant:/config/.storage/lovelace.district
# рестарт стека — только через Komodo
```
