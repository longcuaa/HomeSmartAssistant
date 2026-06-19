"""Lop mong boc paho-mqtt de dieu khien thiet bi va doc cam bien that.

Ket noi lazy, cache lai client. Neu broker o localhost ma khong ket noi duoc thi chuyen
sang che do gia lap (simulated) thay vi raise, de dev chay duoc khi chua co broker. Neu
broker that duoc cau hinh (host khac localhost) ma loi thi bao loi ro rang, khong gia lap
am tham de tranh hieu nham la dang dung thiet bi that.

Giu giao thuc MQTT goi gon o day, tools.py chi goi publish/read_sensor.
"""
import json
import socket
import threading
import config

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

_client = None
_simulated = False
_init_done = False
_lock = threading.Lock()


def _enter_simulation(reason):
    """Vao che do gia lap (chi khi broker o localhost) hoac bao loi ro neu la broker that."""
    global _simulated
    if config.MQTT_HOST == "localhost":
        _simulated = True
        print(f"[CANH BAO] Khong ket noi duoc MQTT broker o localhost ({reason}). "
              f"Chuyen sang che do GIA LAP, KHONG dung thiet bi that.")
    else:
        print(f"[LOI] Khong ket noi duoc MQTT broker {config.MQTT_HOST}:{config.MQTT_PORT} "
              f"({reason}). Lenh thiet bi se that bai.")


def _ensure():
    """Tra ve client da ket noi, hoac None khi gia lap/loi. Ket noi mot lan roi cache."""
    global _client, _init_done
    if _init_done:
        return _client
    with _lock:
        if _init_done:
            return _client
        _init_done = True
        if mqtt is None:
            _enter_simulation("thieu thu vien paho-mqtt")
            return None
        # Kiem tra nhanh broker co mo cong khong, gioi han MQTT_CONNECT_TIMEOUT, de khong treo lau
        # khi broker khong ton tai (vi du cau hoi khong lien quan ma vo tinh cham toi cong cu thiet bi).
        try:
            socket.create_connection(
                (config.MQTT_HOST, config.MQTT_PORT), timeout=config.MQTT_CONNECT_TIMEOUT
            ).close()
        except OSError as e:
            _enter_simulation(f"khong mo duoc {config.MQTT_HOST}:{config.MQTT_PORT} ({e})")
            return None
        try:
            try:
                c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            except (AttributeError, TypeError):
                c = mqtt.Client()  # paho 1.x
            if config.MQTT_USER:
                c.username_pw_set(config.MQTT_USER, config.MQTT_PASSWORD)
            c.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=60)
            c.loop_start()
            _client = c
        except Exception as e:
            _enter_simulation(str(e))
            _client = None
    return _client


def publish(topic, payload):
    """Gui lenh len broker. payload la dict (se json hoa) hoac chuoi. Tra ve True neu gui duoc."""
    c = _ensure()
    if c is None:
        return False
    try:
        data = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        info = c.publish(topic, data)
        info.wait_for_publish(timeout=config.MQTT_TIMEOUT)
        return info.is_published()
    except Exception as e:
        print(f"[LOI] Gui MQTT that bai topic={topic}: {e}")
        return False


def read_sensor(topic, timeout=None):
    """Subscribe mot lan, lay payload dau tien tra ve duoi dang chuoi. None neu het timeout."""
    c = _ensure()
    if c is None:
        return None
    timeout = config.MQTT_TIMEOUT if timeout is None else timeout
    result = {}
    done = threading.Event()

    def _on_message(client, userdata, msg):
        result["payload"] = msg.payload.decode("utf-8", errors="ignore")
        done.set()

    try:
        c.message_callback_add(topic, _on_message)
        c.subscribe(topic)
        got = done.wait(timeout)
        return result.get("payload") if got else None
    except Exception as e:
        print(f"[LOI] Doc cam bien MQTT that bai topic={topic}: {e}")
        return None
    finally:
        try:
            c.unsubscribe(topic)
            c.message_callback_remove(topic)
        except Exception:
            pass


def simulated():
    """True neu dang chay che do gia lap (broker localhost khong ket noi duoc)."""
    _ensure()
    return _simulated


def connected():
    """True neu dang ket noi den mot broker that."""
    return _ensure() is not None
