.DEFAULT_GOAL := all
ZIRAN ?= ziran
LOCK_FLAGS := $(if $(wildcard ziran.local.toml),,--locked)
TOOLCHAIN = $(shell $(ZIRAN) pkg path ziran $(LOCK_FLAGS))
KRYON = $(shell $(ZIRAN) pkg path kryon $(LOCK_FLAGS))
ZIRANC = $(TOOLCHAIN)/build/bin/ziran
MODULES = --module-path '$(KRYON)/src/ui' --module-path '$(KRYON)/src/backend' \
	--module-path 'kryon=$(KRYON)/src/ui' --module-path 'kryon=$(KRYON)/src/backend' \
	--module-path 'std=$(TOOLCHAIN)/std' --module-path '$(TOOLCHAIN)/std'
DESKTOP_LIBS = $$(pkg-config --libs sdl2 cairo freetype2 fontconfig pangocairo) -ldl -lm -lpthread
CFLAGS_ZI = -std=c11 -O2 -ffunction-sections -fdata-sections -I'$(TOOLCHAIN)/include'
# The app as it is installed: the program, its menu assets and the games.
APP := build/app
GAMES := $(APP)/games/animal-count.zib $(APP)/games/dino-paint.zib

.PHONY: all run art sounds test test-ui install

all: $(APP)/jungle $(GAMES) $(APP)/games/catalog.txt $(APP)/assets/jungle/font.png

run: all
	$(APP)/jungle

build/ziran/libziran.a:
	$(MAKE) -C '$(TOOLCHAIN)' BUILD_DIR='$(abspath build/ziran)' '$(abspath $@)'

$(APP)/jungle: $(wildcard host/*.zi retro/*.zi games/paint/paint_palette.zi) build/ziran/libziran.a
	mkdir -p $(APP)
	@set -eu; output=$$(mktemp -d build/host-c.XXXXXX); \
		trap 'rm -rf "$$output"' EXIT; \
		'$(ZIRANC)' build --target=c --root host $(MODULES) --entry main:main -o "$$output" host/main.zi; \
		$${CC:-cc} $(CFLAGS_ZI) $$(find "$$output" -type d -printf ' -iquote %p') $$(find "$$output" -name '*.c') \
		build/ziran/libziran.a -Wl,--gc-sections $(DESKTOP_LIBS) -o "$$output/jungle"; \
		mv "$$output/jungle" $@

$(APP)/games/catalog.txt: games/catalog.txt
	mkdir -p $(APP)/games
	cp $< $@

$(APP)/assets/jungle/font.png: $(wildcard assets/jungle/* assets/jungle/sounds/*)
	mkdir -p $(APP)/assets
	rm -rf $(APP)/assets/jungle
	cp -r assets/jungle $(APP)/assets/jungle

# Each game is its own bundle, carrying only its own pictures and sounds.
$(APP)/games/animal-count.zib: $(wildcard games/animal/*.zi retro/*.zi) $(shell find assets/animal-count -type f)
	rm -rf build/stage/animal-count
	mkdir -p build/stage/animal-count/assets $(APP)/games
	cp -r assets/animal-count build/stage/animal-count/assets/
	'$(ZIRANC)' bundle --root games/animal $(MODULES) --define KRYON_HOSTED_UI \
		--asset-dir assets=build/stage/animal-count/assets --entry animal_count:main -o $@ games/animal/animal_count.zi

$(APP)/games/dino-paint.zib: $(wildcard games/paint/*.zi retro/*.zi) $(shell find assets/dino-paint -type f)
	rm -rf build/stage/dino-paint
	mkdir -p build/stage/dino-paint/assets $(APP)/games
	cp -r assets/dino-paint build/stage/dino-paint/assets/
	'$(ZIRANC)' bundle --root games/paint $(MODULES) --define KRYON_HOSTED_UI \
		--asset-dir assets=build/stage/dino-paint/assets --entry dino_paint:main -o $@ games/paint/dino_paint.zi

# Pixel art: art/*.svg through Inkscape and ImageMagick into assets/
# (committed). Dino Colors' original Bert artwork is committed directly.
art: build/tools/art
	build/tools/art
	python3 tools/paint_pages.py

games/paint/paint_pages.zi: tools/paint_pages.py $(wildcard assets/dino-paint/art/scene[0-9].png assets/dino-paint/art/dino*-s4.png)
	python3 tools/paint_pages.py

# Sound effects into assets/ (committed).
sounds: build/tools/sounds
	build/tools/sounds

build/tools/%: tools/%.zi $(wildcard tools/*.zi) build/ziran/libziran.a
	rm -rf build/tools/$*-c
	'$(ZIRANC)' build --target=c --root tools --module-path 'std=$(TOOLCHAIN)/std' --module-path '$(TOOLCHAIN)/std' \
		--entry $*:main -o build/tools/$*-c $<
	$${CC:-cc} $(CFLAGS_ZI) $$(find build/tools/$*-c -type d -printf ' -iquote %p') $$(find build/tools/$*-c -name '*.c') \
		build/ziran/libziran.a -Wl,--gc-sections -lm -lpthread -o $@

build/tests/%: tests/%_test.zi $(wildcard games/*/*.zi host/*.zi) build/ziran/libziran.a
	rm -rf build/tests/$*-c
	'$(ZIRANC)' build --target=c --root tests $(MODULES) \
		--entry $*_test:main -o build/tests/$*-c $<
	$${CC:-cc} $(CFLAGS_ZI) $$(find build/tests/$*-c -type d -printf ' -iquote %p') $$(find build/tests/$*-c -name '*.c') \
		build/ziran/libziran.a -Wl,--gc-sections -lm -lpthread -o $@

# Questions, painting and PNG pictures, then every game opened in the app.
test: build/tests/paint build/tests/png build/tests/progress build/tests/document build/tests/counting build/tests/printing all
	build/tests/paint
	build/tests/progress
	build/tests/document
	build/tests/counting
	build/tests/png build/tests/check.png
	test "$$(convert build/tests/check.png -format '%w %h %[pixel:p{0,0}] %[pixel:p{2,1}]' info:)" = "3 2 srgb(170,0,0) srgb(255,255,85)"
	rm -rf build/tests/data
	mkdir -p build/tests/data
	printf 'jungle 1\nfruits 4\n' > build/tests/data/progress.txt
	JUNGLE_DATA=$(abspath build/tests/data) $(APP)/jungle --check
	python3 tests/runtime_test.py
	python3 tests/export_test.py
	python3 tests/assets_test.py

# Actual input and rendering on a private display; requires Xvfb, xdotool,
# ImageMagick and Pillow. Never uses the inherited desktop or owner saves.
test-ui: all
	python3 tests/runtime_test.py --ui

BIN_DIR ?= $(HOME)/.local/bin
LIB_DIR ?= $(HOME)/.local/lib/jungle
DATA_DIR ?= $(if $(XDG_DATA_HOME),$(XDG_DATA_HOME),$(HOME)/.local/share)

# The program finds assets/ and games/ beside itself.
install: all
	mkdir -p '$(LIB_DIR)/assets' '$(LIB_DIR)/games' '$(BIN_DIR)' '$(DATA_DIR)/applications' \
		'$(DATA_DIR)/icons/hicolor/64x64/apps'
	cp -r $(APP)/assets/. '$(LIB_DIR)/assets/'
	cp $(APP)/games/*.zib $(APP)/games/catalog.txt '$(LIB_DIR)/games/'
	install -m 0755 $(APP)/jungle '$(LIB_DIR)/jungle.new'
	mv -f '$(LIB_DIR)/jungle.new' '$(LIB_DIR)/jungle'
	ln -sfn '$(LIB_DIR)/jungle' '$(BIN_DIR)/jungle'
	install -m 0644 assets/jungle/icon.png '$(DATA_DIR)/icons/hicolor/64x64/apps/xyz.waozi.jungle.png'
	install -m 0644 packaging/xyz.waozi.jungle.desktop '$(DATA_DIR)/applications/'
