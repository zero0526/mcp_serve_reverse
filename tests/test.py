import puremagic

jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 20

print(puremagic.from_string(jpeg_bytes))
# .jpg

print(puremagic.magic_string(jpeg_bytes))