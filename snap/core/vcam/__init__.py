"""Virtual camera outputs, written from scratch against the devices' shared-memory
interfaces (no third-party virtual camera library)."""
from snap.core.vcam.base import VCamError, VirtualOutput

__all__ = ["VCamError", "VirtualOutput", "devices_registered", "open_output"]

# DirectShow "video input device" category
_VIDEO_INPUT_CATEGORY = r"CLSID\{860BB310-5D01-11d0-BD3B-00A0C911CE86}\Instance"


def devices_registered() -> set[str]:
    """Friendly names of all DirectShow video capture devices on this machine."""
    import winreg
    names = set()
    try:
        root = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, _VIDEO_INPUT_CATEGORY)
    except OSError:
        return names
    with root:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(root, sub) as key:
                    names.add(str(winreg.QueryValueEx(key, "FriendlyName")[0]))
            except OSError:
                continue
    return names


def open_output(backend: str, width: int, height: int, fps: float) -> VirtualOutput:
    from snap.core.vcam import obs, unitycapture

    installed = devices_registered()
    candidates = {"unitycapture": [unitycapture], "obs": [obs]}.get(backend, [unitycapture, obs])
    available = [m for m in candidates if m.DEVICE_NAME in installed]
    if not available:
        raise VCamError("not_installed", "no supported virtual camera driver is installed")
    last = None
    for module in available:
        cls = unitycapture.UnityCaptureOutput if module is unitycapture else obs.OBSOutput
        try:
            return cls(width, height, fps)
        except VCamError as e:
            last = e
    raise last
