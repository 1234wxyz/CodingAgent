"""Verify that classify_temperature returns correct categories."""
from validator import classify_temperature

assert classify_temperature(-5) == "freezing"
assert classify_temperature(10) == "cold"
assert classify_temperature(20) == "comfortable"
assert classify_temperature(30) == "hot", f"Got {classify_temperature(30)!r} instead of 'hot'"
assert classify_temperature(40) == "extreme"
print("PASS")
