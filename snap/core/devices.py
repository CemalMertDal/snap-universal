"""Camera and microphone discovery."""
import cv2

# never offer our own outputs as an input (it would feed back into itself)
OUR_OUTPUTS = ("obs virtual camera", "unity video capture")
# for devices exposed by several Windows audio APIs, keep the most capable one
_API_PREFERENCE = ("Windows WASAPI", "Windows DirectSound", "MME")


def list_cameras() -> list[tuple[int, str]]:
    try:
        from pygrabber.dshow_graph import FilterGraph
        names = FilterGraph().get_input_devices()
        cams = [(i, n) for i, n in enumerate(names) if not any(o in n.lower() for o in OUR_OUTPUTS)]
        if cams or names:
            return cams
    except Exception:
        pass
    cams = []
    for i in range(5):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            cams.append((i, f"Camera {i}"))
        cap.release()
    return cams


def list_mics() -> list[tuple[int, str]]:
    try:
        import sounddevice as sd
        apis = [a["name"] for a in sd.query_hostapis()]
        inputs = [(i, d, apis[d["hostapi"]]) for i, d in enumerate(sd.query_devices())
                  if d["max_input_channels"] > 0]
        # WASAPI lists only real endpoints (no "sound mapper" style pseudo devices)
        if any(api == _API_PREFERENCE[0] for _, _, api in inputs):
            inputs = [x for x in inputs if x[2] == _API_PREFERENCE[0]]
        best: dict[str, tuple[int, int, str]] = {}
        for i, d, api in inputs:
            if api not in _API_PREFERENCE:
                continue
            rank = _API_PREFERENCE.index(api)
            name = d["name"].strip()
            key = name[:31].lower()          # MME truncates names to 31 characters
            if key not in best or rank < best[key][1]:
                best[key] = (i, rank, name)
        return sorted(((i, name) for i, _, name in best.values()), key=lambda x: x[1].lower())
    except Exception:
        return []


def default_mic() -> int | None:
    try:
        import sounddevice as sd
        default = sd.default.device[0]
        if default is None or default < 0:
            return None
        name = sd.query_devices(default)["name"].strip()[:31].lower()
        for i, label in list_mics():
            if label[:31].lower() == name:
                return i
    except Exception:
        pass
    return None
