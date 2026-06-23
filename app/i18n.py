"""Bilingual interface — Russian (default) / English translation system."""

# Current language: 'ru' or 'en'
_lang = 'ru'

_STRINGS = {
    # ── Window title ──
    'window_title': ('TL.0009 ОПУ — ТехЛазер', 'TL.0009 OPU — TechLaser'),

    # ── Menu bar ──
    'menu_devices': ('&Устройства', '&Devices'),
    'menu_view': ('&Вид', '&View'),
    'menu_language': ('&Язык', '&Language'),
    'menu_pt_conn': ('Подключение PAN-TILT...', 'PAN-TILT Connection...'),
    'menu_laser_conn': ('Подключение ЛАЗЕР...', 'LASER Connection...'),
    'menu_cameras_win': ('Окно камер', 'Cameras Window'),
    'menu_map_win': ('Окно карты', 'Map Window'),
    'menu_log_win': ('Журнал протокола', 'Protocol Log'),
    'lang_russian': ('Русский', 'Русский'),
    'lang_english': ('English', 'English'),

    # ── Left panel sections ──
    'sec_device_status': ('СТАТУС УСТРОЙСТВ', 'DEVICE STATUS'),
    'sec_speed_setting': ('НАСТРОЙКА СКОРОСТИ', 'SPEED SETTING'),
    'sec_goto_position': ('ПЕРЕЙТИ К ПОЗИЦИИ', 'GO TO POSITION'),
    'sec_tilt_diag': ('НАКЛОН И ДИАГНОСТИКА', 'TILT & DIAGNOSTICS'),

    # ── Left panel labels ──
    'pan_speed': ('СКОРОСТЬ PAN °/с', 'PAN SPEED °/s'),
    'tilt_speed': ('СКОРОСТЬ TILT °/с', 'TILT SPEED °/s'),
    'pan_deg': ('PAN °:', 'PAN °:'),
    'tilt_deg': ('TILT °:', 'TILT °:'),
    'invert_tilt': ('Инвертировать ось TILT', 'Invert TILT axis'),

    # ── Left panel buttons ──
    'btn_go': ('ПЕРЕЙТИ', 'GO'),
    'btn_stop_all': ('ОСТАНОВИТЬ ВСЁ', 'STOP ALL'),
    'btn_home': ('ДОМОЙ (0° / 0°)', 'HOME (0° / 0°)'),
    'btn_pan_diag': ('ДИАГН. PAN', 'PAN DIAG'),
    'btn_tilt_diag': ('ДИАГН. TILT', 'TILT DIAG'),

    # ── Right panel sections ──
    'sec_control_pad': ('ПАНЕЛЬ УПРАВЛЕНИЯ', 'CONTROL PAD'),
    'sec_laser_rangefinder': ('ЛАЗЕРНЫЙ ДАЛЬНОМЕР', 'LASER RANGEFINDER'),
    'sec_detection': ('ДЕТЕКЦИЯ', 'DETECTION'),

    # ── Right panel labels ──
    'lbl_no_target': ('НЕТ ЦЕЛИ', 'NO TARGET'),
    'lbl_model_not_loaded': ('Модель: Не загружена', 'Model: Not Loaded'),
    'lbl_filter': ('Фильтр:', 'Filter:'),
    'lbl_fps': ('FPS: --', 'FPS: --'),

    # ── Right panel buttons ──
    'btn_single': ('ОДИН', 'SINGLE'),
    'btn_cont': ('НЕПР.', 'CONT'),
    'btn_stop': ('СТОП', 'STOP'),
    'btn_selfcheck': ('САМОДИАГН.', 'SELF-CHECK'),
    'btn_connect': ('ПОДКЛЮЧИТЬ', 'CONNECT'),
    'btn_detect': ('ДЕТЕКЦИЯ', 'DETECT'),
    'btn_track': ('ТРЕКИНГ', 'TRACK'),
    'btn_auto_lock': ('АВТО-ЗАХВАТ', 'AUTO-LOCK'),
    'btn_next': ('СЛЕД.', 'NEXT'),
    'btn_stop_tracking': ('СТОП ТРЕКИНГ', 'STOP TRACKING'),

    # ── Detection filter combo ──
    'filter_all': ('Все классы', 'All Classes'),
    'filter_air': ('Воздушные цели', 'Air Targets'),
    'filter_drone_vehicle': ('Дроны + Техника', 'Drones + Vehicles'),

    # ── Dashboard ──
    'dash_title': ('ПРИБОРНАЯ ПАНЕЛЬ', 'DASHBOARD'),
    'dash_idle': ('ПОКОЙ', 'IDLE'),
    'dash_moving': ('ДВИЖЕНИЕ', 'MOVING'),
    'dash_no_target': ('НЕТ ЦЕЛИ', 'NO TARGET'),

    # ── Device state bar ──
    'state_idle': ('ПОКОЙ', 'IDLE'),
    'state_moving': ('ДВИЖЕНИЕ', 'MOVING'),

    # ── Status indicators ──
    'status_off': ('ВЫКЛ', 'OFF'),
    'status_on': ('ВКЛ', 'ON'),
    'status_err': ('ОШИБКА', 'ERR'),

    # ── Floating windows ──
    'win_cameras': ('КАМЕРЫ', 'CAMERAS'),
    'win_map': ('КАРТА', 'MAP'),
    'win_log': ('Журнал протокола', 'Protocol Log'),
    'btn_beam_config': ('НАСТРОЙКА ЛУЧА', 'BEAM CONFIG'),

    # ── Camera overlay buttons ──
    'ov_lsr': ('LSR', 'LSR'),
    'ov_det': ('DET', 'DET'),
    'ov_trk': ('TRK', 'TRK'),
    'ov_flt': ('FLT', 'FLT'),
    'ov_pal': ('PAL', 'PAL'),
    'ov_tmp': ('TMP', 'TMP'),

    # ── Zoom toolbar ──
    'zoom_label': ('ЗУМ', 'ZOOM'),
    'zoom_tele': ('ТЕЛЕ +', 'TELE +'),
    'zoom_wide': ('ШИРОКИЙ -', 'WIDE -'),
    'focus_near': ('БЛИЖЕ', 'NEAR'),
    'focus_far': ('ДАЛЬШЕ', 'FAR'),
    'focus_auto': ('АВТО ФОКУС', 'AUTO FOCUS'),

    # ── Dialogs ──
    'dlg_validation': ('Проверка', 'Validation'),
    'dlg_empty_field': ('не может быть пустым', 'cannot be empty'),
    'dlg_invalid_port': ('должен быть 1-65535', 'must be 1-65535'),
    'dlg_beam_lat': ('Широта луча', 'Beam Latitude'),
    'dlg_beam_lng': ('Долгота луча', 'Beam Longitude'),
    'dlg_beam_offset': ('Смещение (град):', 'Offset (deg):'),
    'dlg_beam_length': ('Длина (м):', 'Length (m):'),
    'dlg_zoom_speed': ('Скорость зума', 'Zoom Speed'),
    'dlg_zoom_speed_prompt': ('Скорость зума (%):', 'Zoom speed (%):'),
    'dlg_track_gain': ('Коэффициент трекинга', 'Tracking Gain'),
    'dlg_track_gain_prompt': ('Пропорц. коэффициент:', 'Proportional gain:'),
    'dlg_latitude': ('Широта:', 'Latitude:'),
    'dlg_longitude': ('Долгота:', 'Longitude:'),

    # ── Cameras menu ──
    'cam_menu_connection': ('Подключение', 'Connection'),
    'cam_menu_settings': ('Настройки', 'Settings'),
    'cam_menu_cam1': ('CAM1 (IP камера)...', 'CAM1 (IP Camera)...'),
    'cam_menu_cam2': ('CAM2 (Тепловизор)...', 'CAM2 (Thermal)...'),
    'cam_menu_zoom': ('ЗУМ камера (ONVIF)...', 'ZOOM Camera (ONVIF)...'),
    'cam_menu_reticle': ('Прицельная сетка', 'Reticle'),
    'cam_menu_det_filter': ('Фильтр детекции', 'Detection Filter'),
    'cam_menu_zoom_speed': ('Скорость зума...', 'Zoom Speed...'),
    'cam_menu_track_gain': ('Коэф. трекинга...', 'Tracking Gain...'),
    'reticle_crosshair': ('Перекрестие', 'Crosshair'),
    'reticle_mildot': ('Mil-Dot', 'Mil-Dot'),
    'reticle_combat': ('Боевой', 'Combat'),

    # ── Detection dynamic states ──
    'btn_stop_det': ('СТОП ДЕТЕКЦИЯ', 'STOP DET'),
    'btn_stop_trk': ('СТОП ТРЕКИНГ', 'STOP TRK'),
    'lbl_loading': ('Загрузка...', 'Loading...'),
    'lbl_model_prefix': ('Модель: ', 'Model: '),
    'lbl_locked': ('ЗАХВАТ', 'LOCKED'),
    'status_ready': ('Готово', 'Ready'),
    'map_device_pos': ('Устройство: {lat:.4f}, {lng:.4f}', 'Device: {lat:.4f}, {lng:.4f}'),
    'dlg_pt_conn': ('Подключение PAN-TILT', 'PAN-TILT Connection'),
    'dlg_laser_conn': ('Подключение ЛАЗЕР', 'LASER Connection'),
    'dlg_cam1': ('CAM1 — IP камера', 'CAM1 — IP Camera'),
    'dlg_cam2': ('CAM2 — Тепловизор', 'CAM2 — Thermal Camera'),
    'dlg_zoom_onvif': ('ЗУМ камера — ONVIF', 'ZOOM Camera — ONVIF'),
    'laser_out_of_range': ('ВНЕ ДИАПАЗОНА', 'OUT OF RANGE'),
    'laser_target': ('ЦЕЛЬ', 'TARGET'),
    'laser_near': ('БЛИЗКО', 'NEAR'),
    'laser_far': ('ДАЛЕКО', 'FAR'),
    'laser_stop_cont': ('СТОП НЕПР.', 'STOP CONT'),
    'det_locked_fmt': ('{locked}: #{id} {cls}', '{locked}: #{id} {cls}'),
    'det_lost_fmt': ('ЦЕЛЬ #{id} ПОТЕРЯНА', 'TARGET #{id} LOST'),
    'det_tracking_fmt': ('{locked}: #{id} {cls} {conf}', '{locked}: #{id} {cls} {conf}'),
    'reticle_crosshair_log': ('Перекрестие', 'Crosshair'),
    'reticle_mildot_log': ('Mil-Dot', 'Mil-Dot'),
    'reticle_combat_log': ('Боевой', 'Combat'),
}


def tr(key):
    """Get translated string for current language.

    Args:
        key: Translation key string.

    Returns:
        Translated string, or key itself if not found.
    """
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    idx = 0 if _lang == 'ru' else 1
    return entry[idx]


def set_language(lang):
    """Set current language ('ru' or 'en')."""
    global _lang
    _lang = lang if lang in ('ru', 'en') else 'ru'


def get_language():
    """Get current language ('ru' or 'en')."""
    return _lang


def toggle_language():
    """Toggle between 'ru' and 'en'. Returns new language."""
    global _lang
    _lang = 'en' if _lang == 'ru' else 'ru'
    return _lang
