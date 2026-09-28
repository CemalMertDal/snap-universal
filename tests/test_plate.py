import numpy as np

from snap.core.plate import PlateBuilder


def _room(h=120, w=160, seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, (h, w, 3), dtype=np.uint8)


def test_median_removes_a_passing_object():
    room = _room()
    pb = PlateBuilder(needed=15, min_ok=5)
    empty = np.zeros(room.shape[:2], np.float32)
    for i in range(15):
        frame = room.copy()
        if i % 3 == 0:                                  # something passes in 5 of 15 frames
            frame[40:80, 60:100] = (0, 255, 0)
        pb.add(frame, empty)
    assert pb.done and pb.accepted == 15
    plate = pb.build()
    assert np.array_equal(plate, room)


def test_frames_with_a_person_are_rejected():
    room = _room()
    person = np.zeros(room.shape[:2], np.float32)
    person[20:100, 50:110] = 1.0
    pb = PlateBuilder(needed=15, min_ok=5, max_cover=0.015)
    for i in range(15):
        pb.add(room, person if i < 12 else np.zeros_like(person))
    assert pb.done and pb.accepted == 3
    assert pb.build() is None


def test_not_done_until_enough_attempts():
    pb = PlateBuilder(needed=3)
    room = _room()
    empty = np.zeros(room.shape[:2], np.float32)
    pb.add(room, empty)
    assert not pb.done
    pb.add(room, empty)
    pb.add(room, empty)
    assert pb.done
