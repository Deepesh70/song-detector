import pytest
from client.fingerprinter import (
    pack_hash,
    unpack_hash,
    to_signed_int32,
    from_signed_int32,
    TARGET_ZONE_T_MIN,
    TARGET_ZONE_T_MAX,
)


def test_bit_packing_boundaries():
    """Verify bit packing and unpacking across minimum and maximum boundaries."""
    # Min bounds
    f1_min, f2_min, dt_min = 0, 0, TARGET_ZONE_T_MIN
    u32_min = pack_hash(f1_min, f2_min, dt_min)
    assert u32_min == 0
    assert unpack_hash(u32_min) == (f1_min, f2_min, dt_min)

    # Max bounds
    f1_max, f2_max, dt_max = 1023, 1023, TARGET_ZONE_T_MAX
    u32_max = pack_hash(f1_max, f2_max, dt_max)
    # 10 bits f1 (1111111111) << 22 | 10 bits f2 (1111111111) << 12 | 8 bits dt (11111111) << 4 | 0000
    assert u32_max == 0xFFFF_FFF0
    assert unpack_hash(u32_max) == (f1_max, f2_max, dt_max)


def test_no_bit_bleeding():
    """Verify that setting individual fields does not bleed into adjacent fields."""
    # Only f1 set
    h_f1 = pack_hash(512, 0, TARGET_ZONE_T_MIN)
    f1, f2, dt = unpack_hash(h_f1)
    assert f1 == 512
    assert f2 == 0
    assert dt == TARGET_ZONE_T_MIN

    # Only f2 set
    h_f2 = pack_hash(0, 512, TARGET_ZONE_T_MIN)
    f1, f2, dt = unpack_hash(h_f2)
    assert f1 == 0
    assert f2 == 512
    assert dt == TARGET_ZONE_T_MIN

    # Only dt set
    h_dt = pack_hash(0, 0, TARGET_ZONE_T_MIN + 128)
    f1, f2, dt = unpack_hash(h_dt)
    assert f1 == 0
    assert f2 == 0
    assert dt == TARGET_ZONE_T_MIN + 128


def test_signed_int32_casting():
    """Verify two's complement conversion between unsigned uint32 and PostgreSQL signed int32."""
    # 0 -> 0
    assert to_signed_int32(0) == 0
    assert from_signed_int32(0) == 0

    # Max positive int32 (0x7FFFFFFF = 2147483647)
    pos_max = 0x7FFF_FFFF
    assert to_signed_int32(pos_max) == 2147483647
    assert from_signed_int32(2147483647) == pos_max

    # Min negative int32 (0x80000000 = -2147483648)
    neg_min = 0x8000_0000
    assert to_signed_int32(neg_min) == -2147483648
    assert from_signed_int32(-2147483648) == neg_min

    # All ones (0xFFFFFFFF = -1)
    all_ones = 0xFFFF_FFFF
    assert to_signed_int32(all_ones) == -1
    assert from_signed_int32(-1) == all_ones


def test_out_of_bounds_validation():
    """Verify that invalid inputs raise ValueError."""
    with pytest.raises(ValueError):
        pack_hash(1024, 0, 10)  # f1 > 1023

    with pytest.raises(ValueError):
        pack_hash(0, 1024, 10)  # f2 > 1023

    with pytest.raises(ValueError):
        pack_hash(0, 0, TARGET_ZONE_T_MIN - 1)  # dt < 3

    with pytest.raises(ValueError):
        pack_hash(0, 0, TARGET_ZONE_T_MAX + 1)  # dt > 258
