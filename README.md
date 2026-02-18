# Deep Link Apple TV MVP

A web application for controlling Apple TV devices via deep links, built with SvelteKit frontend and FastAPI backend using pyatv library.

## Features

- **Device Discovery**: Scan for Apple TV devices on your local network using mDNS/Bonjour
- **Device Pairing**: Pair with Apple TV devices using AirPlay, Companion, or MRP protocols
- **URL Playback**: Send URLs (deep links or media URLs) to Apple TV for playback
- **Deep Link Support**: Launch apps and content via deep links (Netflix, Disney+, HBO Max, Apple TV+, etc.)
- **Device Management**: Set default Apple TV device and manage paired devices
- **Modern UI**: Clean, responsive interface built with SvelteKit and Tailwind CSS

## Apple TV Compatibility

**Supported Models:**
- ✅ **Apple TV 3rd generation (A1469)** — AirPlay для воспроизведения медиа по URL
- ✅ Apple TV 2nd generation and later (AirPlay support)
- ✅ Apple TV 4th generation (tvOS) and later (AirPlay + deep links)
- ⚠️ Apple TV 1st generation (limited support - see below)

**Apple TV 3rd generation (модель A1469):**
- Поддерживается **AirPlay** — можно отправлять прямые ссылки на медиа (`.mp4`, `.m3u8` и т.д.)
- Сопряжение по протоколу **AirPlay**
- Deep links (Netflix, Disney+ и т.д.) обычно **не поддерживаются** — для них нужен Apple TV 4-го поколения (tvOS) и протокол Companion
- Если AirPlay не срабатывает: проверьте сеть, формат видео и что устройство сопряжено

**Apple TV 1st Generation:**
Apple TV 1st generation (2007) does not support AirPlay or modern protocols. The app will detect this and provide information about the device, but direct URL playback is not available.

## Prerequisites

- **Docker** and **Docker Compose** installed
- **mDNS/Bonjour** support:
  - **Linux**: Avahi daemon (usually pre-installed)
  - **macOS**: Bonjour (built-in)
  - **Windows**: Bonjour Print Services (may need installation)
- Apple TV device on the same local network
- Network access for multicast DNS (mDNS) discovery

## Architecture

```
┌─────────────────┐         ┌─────────────────┐         ┌──────────────┐
│  SvelteKit App  │ ──────> │   FastAPI       │ ──────> │   SQLite     │
│   (Port 3000)   │  HTTP   │   (Port 8000)   │         │   Database   │
└─────────────────┘         └─────────────────┘         └──────────────┘
                                      │
                                      │ (host network)
                                      ▼
                              ┌──────────────┐
                              │   pyatv      │
                              │   Library    │
                              └──────────────┘
                                      │
                                      │ (mDNS/Bonjour)
                                      ▼
                              ┌──────────────┐
                              │  Apple TV    │
                              │  (Local LAN) │
                              └──────────────┘
```

## Quick Start

1. **Clone the repository** (if applicable) or navigate to the project directory

2. **Start the services**:
   ```bash
   docker compose up --build
   ```

3. **Access the application**:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## Usage

### Pairing an Apple TV Device

#### Пошаговая инструкция по сопряжению:

1. **Откройте приложение** в браузере (http://localhost:3000)
2. **Откройте настройки**: Нажмите кнопку ⚙ (Настройки) на главной странице
3. **Найдите ваше устройство**:
   - **Вариант А**: Нажмите "Сканировать устройства" и дождитесь появления Apple TV в списке
   - **Вариант Б**: Если сканирование не находит устройство, нажмите "Добавить вручную":
     - Введите IP-адрес Apple TV (например, `192.168.1.100`)
     - При необходимости укажите название устройства
     - Нажмите "Добавить устройство"
4. **Выберите протокол** для сопряжения:
   - **Apple TV 3rd generation (A1469)**: Используйте **AirPlay** (для воспроизведения медиа по URL)
   - **Apple TV 4th generation (tvOS)**: Доступны AirPlay и Companion/MRP (для deep links)
   - **Примечание**: Apple TV 1st generation не поддерживает сопряжение
5. **Начните сопряжение**: Нажмите кнопку "Сопряжение" рядом с выбранным протоколом
6. **Введите PIN**: 
   - На экране Apple TV появится 4-значный PIN (например, `1234`)
   - Введите PIN в появившемся поле в приложении
   - Нажмите "Подтвердить"
7. **Проверка**: При успешном сопряжении появится уведомление "Сопряжение завершено успешно"
8. **Установите устройство по умолчанию** (опционально):
   - В списке сопряженных устройств нажмите "Установить по умолчанию"
   - Это позволит отправлять ссылки без выбора устройства каждый раз

#### Важные моменты:

- **Убедитесь**, что Apple TV включен и находится в той же сети Wi‑Fi, что и компьютер
- **PIN** вводите точно так, как показано на экране Apple TV (обычно 4 цифры)
- **Для Apple TV 3rd generation (A1469)**: Используйте протокол AirPlay — он поддерживает воспроизведение медиа по URL, но не поддерживает deep links (для них нужен Apple TV 4th generation с tvOS)
- **Для Apple TV 1st generation**: Устройство не поддерживает сопряжение или современные протоколы — прямое воспроизведение URL недоступно

### Sending URLs to Apple TV

1. Enter a URL in the "URL / диплинк" input field
   - **Deep Links**: Supported for Apple TV apps (Netflix, Disney+, HBO Max, Apple TV+, YouTube, etc.)
     - Example: `https://www.netflix.com/title/80234304`
     - Example: `https://tv.apple.com/show/severance/...`
   - **Media URLs**: Direct media files (`.mp4`, `.m3u8`, etc.) will be played via AirPlay. Ссылки на **HLS** (`.m3u8`) сервер принимает и отдаёт как **MP4** (remux через ffmpeg), чтобы Apple TV получал один поток — так же, как для YouTube при 720p/1080p. Нужен корректный `STREAM_BASE_URL`, чтобы Apple TV мог запросить поток.
2. Click "Отправить на Apple TV" (Send to Apple TV)
3. The URL will be launched/played on your default Apple TV device
   - Deep links are launched via the Apps interface
   - Media URLs are played via AirPlay streaming

### Setting Default Device

1. Open Settings (⚙ button)
2. Find your paired device in the list
3. Click "Установить по умолчанию" (Set as default)

### Пересборка потока на сервере (720p/1080p со звуком)

Для YouTube при выборе **720p** или **1080p** бэкенд может склеивать видео- и аудиопоток через **ffmpeg** и отдавать один поток на Apple TV (со звуком). Для этого Apple TV должен иметь доступ по HTTP к бэкенду.

- Задайте переменную **`STREAM_BASE_URL`** — URL, по которому Apple TV сможет запросить поток (обычно это IP вашего ПК в локальной сети и порт 8000).
- Пример: на хосте с IP `192.168.1.5` и портом 8000 задайте в `docker-compose.yml` или в `.env`:
  ```bash
  STREAM_BASE_URL=http://192.168.1.5:8000
  ```
- Перезапустите контейнеры. После этого при выборе 720p/1080p для YouTube будет использоваться склейка на сервере и воспроизведение со звуком.

**Как понять, что склейка работает**

1. **Журнал на странице** — внизу страницы в блоке «Журнал операций со ссылками» после успешной отправки YouTube 720p/1080p в сообщении должно быть: **«качество: 1080p • склейка на сервере»**. Если видите только «качество: 1080p» без «склейка на сервере» — использовался один поток (часто без звука).
2. **По звуку** — включите на Apple TV воспроизведение с качеством 1080p: если слышен звук, склейка работает. Если картинка 1080p, но звука нет — Apple TV не достучался до `STREAM_BASE_URL` или merge не сработал.
3. **Логи бэкенда** — в логах контейнера должна быть строка `Using server merge stream (quality: 1080p)`. Ошибки merge: `Merge fallback failed` или отсутствие этой строки при 1080p.
4. **Проверка STREAM_BASE_URL** — с другого устройства в той же Wi‑Fi откройте в браузере `http://<ваш_STREAM_BASE_URL>/health` (например `http://192.168.100.122:8000/health`). Должен вернуться `{"status":"ok"}`. Если страница не открывается — Apple TV тоже не сможет загрузить поток.

**Если на Apple TV «An error occurred loading» при 1080p (склейка):**
- Убедитесь, что `STREAM_BASE_URL` — IP вашего Mac/ПК в той же сети, что и Apple TV (не `localhost`). Проверьте доступность по пункту 4 выше.
- Первые байты потока могут приходить с задержкой (подключение к YouTube). Перезапустите воспроизведение или попробуйте 720p — иногда загружается быстрее.

### Удаление и изменение устройств

1. Откройте Настройки (⚙)
2. В блоке **«Добавленные устройства»** у каждого устройства доступны:
   - **Изменить** — изменить название и/или IP-адрес (появится форма с полями «Название» и «IP-адрес», кнопки «Сохранить» / «Отмена»)
   - **Удалить** — удалить устройство из списка (подтверждение в диалоге). Если это было устройство по умолчанию, оно снимается с умолчания

## Docker Networking Configuration

### Linux

The `docker-compose.yml` uses `network_mode: host` for the backend service, which allows direct access to the host network for mDNS/Bonjour discovery. This is the simplest configuration and works out of the box.

### macOS/Windows Docker Desktop

On macOS and Windows, `network_mode: host` is not supported. You have two options:

**Option 1: Bridge Network (Recommended)**

1. Comment out `network_mode: host` in `docker-compose.yml`
2. Uncomment the `networks` and `extra_hosts` sections
3. Restart containers:
   ```bash
   docker compose down
   docker compose up --build
   ```

**Option 2: Use Host Network (macOS only)**

On macOS, you can use `host.docker.internal` to access the host network. Update the backend service to use bridge network and configure `extra_hosts`.

## Troubleshooting

### Devices Not Found During Scan

**Problem**: No Apple TV devices appear when scanning.

**Solutions**:
1. **Check Network**: Ensure your computer and Apple TV are on the same local network
2. **Check mDNS/Bonjour**:
   - Linux: Ensure Avahi daemon is running: `systemctl status avahi-daemon`
   - macOS: Bonjour should be enabled by default
   - Windows: Install Bonjour Print Services if not installed
3. **Check Firewall**: Ensure UDP port 5353 (mDNS) is not blocked
4. **VLAN Issues**: If using VLANs, ensure multicast traffic is allowed
5. **Docker Network**: On macOS/Windows, ensure bridge network is properly configured

### Pairing Fails

**Problem**: Pairing process fails or PIN is rejected.

**Solutions**:
1. Ensure you're entering the correct PIN shown on Apple TV
2. Try a different protocol (AirPlay vs Companion vs MRP)
3. Check that the Apple TV is awake and on the same network
4. Restart the Apple TV if pairing consistently fails

### URL Playback Fails

**Problem**: URLs don't play on Apple TV.

**Solutions**:
1. **Deep Links**: 
   - Ensure Companion protocol is paired (required for app launching)
   - Deep links work for supported apps (Netflix, Disney+, HBO Max, Apple TV+, YouTube)
   - Copy deep links from iOS/macOS app "Share" feature for best results
2. **Media URLs**: 
   - Use direct media URLs (`.mp4`, `.m3u8`, etc.) for AirPlay playback
   - Ensure AirPlay is available and paired on the device
3. **Device State**: Ensure Apple TV is awake and ready
4. **Network**: Check network connectivity between backend and Apple TV
5. **Authentication**: Some apps may require authentication - ensure you're logged in on Apple TV

### Backend Can't Access Local Network (macOS/Windows)

**Problem**: Backend container can't discover devices on local network.

**Solutions**:
1. Use bridge network configuration (see Docker Networking section)
2. Ensure `extra_hosts` is configured correctly
3. Check Docker Desktop network settings
4. Try running backend directly on host (outside Docker) for testing

### Database Errors

**Problem**: SQLite database errors or permission issues.

**Solutions**:
1. Ensure volume mounts are configured correctly in `docker-compose.yml`
2. Check file permissions on `appletv.db`
3. Delete `appletv.db` and restart to recreate database

## Development

### Backend Development

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev
```

### Environment Variables

**Backend**:
- `DATABASE_URL`: SQLite database URL (default: `sqlite:///./appletv.db`)

**Frontend**:
- `PUBLIC_API_URL`: Backend API URL (default: `http://localhost:8000`)

## API Endpoints

- `GET /api/appletv/scan` - Scan for Apple TV devices
- `GET /api/appletv/devices` - Get list of paired devices
- `POST /api/appletv/{device_id}/pair/start` - Start pairing process
- `POST /api/appletv/{device_id}/pair/pin` - Submit PIN for pairing
- `POST /api/appletv/play` - Play URL on default device
- `POST /api/appletv/default` - Set default device
- `GET /api/appletv/default` - Get default device

See http://localhost:8000/docs for interactive API documentation.

## Security Notes

- **Credentials**: All Apple TV credentials are stored securely in the backend database
- **Frontend**: Never receives sensitive credential data
- **CORS**: Currently configured for local development (allows all origins)
- **Authentication**: No authentication in MVP (can be added later for production)

## Limitations

- **URL Types**: Works best with direct media URLs; generic web pages may not work
- **Deep Links**: Deep link support depends on Apple TV app availability
- **Network**: Requires local network access and mDNS/Bonjour support
- **Single User**: MVP supports single global default device (can be extended)

## License

This project is provided as-is for MVP purposes.

## Support

For issues related to:
- **pyatv**: See [pyatv documentation](https://pyatv.dev/)
- **Docker networking**: See Docker Desktop documentation for your platform
- **mDNS/Bonjour**: See platform-specific Bonjour/mDNS documentation
