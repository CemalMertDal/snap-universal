import numpy as np

from snap.core.plate import PlateBuilder


def _room(h=120, w=160, seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, (h, w, 3), dtype=np.uint8)


def test_median_removes_a_passing_object():
    room = _room()
    pb = PlateBuilder(needed=15)
    for i in range(15):
        frame = room.copy()
        if i % 3 == 0:                                  # something passes in 5 of 15 frames
            frame[40:80, 60:100] = (0, 255, 0)
        pb.add(frame)
    assert pb.done
    assert np.array_equal(pb.build(), room)


def test_someone_standing_in_the_room_does_not_block_capture():
    room = _room()
    room[20:100, 50:110] = (30, 60, 200)                # a person who stays put the whole time
    pb = PlateBuilder(needed=15)
    for _ in range(15):
        pb.add(room)
    assert np.array_equal(pb.build(), room)


def test_not_done_until_enough_frames():
    pb = PlateBuilder(needed=3)
    room = _room()
    pb.add(room)
    assert not pb.done
    pb.add(room)
    pb.add(room)
    assert pb.done


def test_build_without_frames_returns_none():
    assert PlateBuilder().build() is None
