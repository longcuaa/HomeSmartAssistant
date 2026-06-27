"""Sinh cau tra loi tieng Viet lich su (co dau) cho quan gia.

Tach rieng de Tier 1 (FST) va Tier 3 (fallback khi loi) dung chung mot giong noi: xung 'toi',
goi chu nha theo 'address_style' (mac dinh 'ong/ba'). Day la chuoi NOI RA -> co dau.
"""

# Map device_type -> tu mo ta (co dau) cho cau noi neu can.
_ACTION_VERB = {"ON": "bật", "OFF": "tắt"}


class Phraser:
    def __init__(self, cfg):
        self.addr = cfg.get("butler.address_style", "ông/bà")

    def confirm_control(self, action, device_name):
        verb = _ACTION_VERB.get(action, "điều chỉnh")
        return f"Dạ, tôi sẽ {verb} {device_name} ngay ạ."

    def confirm_temp(self, device_name, temp):
        return f"Dạ, tôi sẽ chỉnh {device_name} xuống {temp} độ ạ."

    def confirm_volume(self, direction, device_name):
        verb = "tăng" if direction == "up" else "giảm"
        return f"Dạ, tôi sẽ {verb} âm lượng {device_name} ạ."

    def confirm_group(self, action, n):
        verb = _ACTION_VERB.get("ON" if action == "GROUP_ON" else "OFF", "điều chỉnh")
        return f"Dạ, tôi sẽ {verb} {n} thiết bị ngay ạ."

    def ask_room(self, action, device_word, rooms_text):
        verb = _ACTION_VERB.get(action, "điều chỉnh")
        return f"Dạ, {self.addr} muốn {verb} {device_word} ở phòng nào ạ: {rooms_text}?"

    def not_found(self, device_word):
        return f"Dạ, xin lỗi, tôi không tìm thấy thiết bị '{device_word}' trong nhà ạ."

    def status(self, device_name, on, temp=None):
        s = "đang bật" if on else "đang tắt"
        if temp is not None and on:
            s += f", {temp} độ"
        return f"Dạ, {device_name} hiện {s} ạ."

    def clarify(self):
        return f"Dạ, xin lỗi, {self.addr} có thể nói rõ hơn ý mình được không ạ?"
