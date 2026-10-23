.DEFAULT_GOAL := all
ZIRAN ?= ziran
LOCK_FLAGS := $(if $(wildcard ziran.local.toml),,--locked)
TOOLCHAIN = $(shell $(ZIRAN) pkg path ziran $(LOCK_FLAGS))
KRYON = $(shell $(ZIRAN) pkg path kryon $(LOCK_FLAGS))
ZIRANC = $(TOOLCHAIN)/build/bin/ziran
MODULES = --module-path '$(KRYON)/src/ui' --module-path '$(KRYON)/src/backend' \
	--module-path 'kryon=$(KRYON)/src/ui' --module-path 'kryon=$(KRYON)/src/backend' \
	--module-path 'std=$(TOOLCHAIN)/std' --module-path '$(TOOLCHAIN)/std'
DESKTOP_LIBS = $$(pkg-config --libs sdl2 cairo freetype2 fontconfig pangocairo) -lm -lpthread
CFLAGS_ZI = -std=c11 -O2 -ffunction-sections -fdata-sections -I'$(TOOLCHAIN)/include'

.PHONY: all art sounds

all: build/jungle

build/ziran/libziran.a:
	$(MAKE) -C '$(TOOLCHAIN)' BUILD_DIR='$(abspath build/ziran)' '$(abspath $@)'

build/jungle: $(wildcard src/*.zi) build/ziran/libziran.a
	rm -rf build/c
	'$(ZIRANC)' build --target=c --root src $(MODULES) --entry main:main -o build/c src/main.zi
	$${CC:-cc} $(CFLAGS_ZI) $$(find build/c -type d -printf ' -iquote %p') $$(find build/c -name '*.c') \
		build/ziran/libziran.a -Wl,--gc-sections $(DESKTOP_LIBS) -o $@.new
	mv $@.new $@

# Pictures: art/*.svg through Inkscape into assets/ (committed).
art: build/tools/art
	build/tools/art

build/tools/art: tools/art.zi build/ziran/libziran.a
	rm -rf build/tools/art-c
	'$(ZIRANC)' build --target=c --root tools --module-path 'std=$(TOOLCHAIN)/std' --module-path '$(TOOLCHAIN)/std' \
		--entry art:main -o build/tools/art-c tools/art.zi
	$${CC:-cc} $(CFLAGS_ZI) $$(find build/tools/art-c -type d -printf ' -iquote %p') $$(find build/tools/art-c -name '*.c') \
		build/ziran/libziran.a -Wl,--gc-sections -lm -lpthread -o $@

.PHONY: test
test: build/tests/lessons build/tests/dino
	build/tests/lessons
	build/tests/dino

build/tests/lessons: tests/lessons_test.zi $(wildcard src/*.zi) build/ziran/libziran.a
	rm -rf build/tests/lessons-c
	'$(ZIRANC)' build --target=c --root . --module-path 'std=$(TOOLCHAIN)/std' --module-path '$(TOOLCHAIN)/std' \
		--entry lessons_test:main -o build/tests/lessons-c tests/lessons_test.zi
	$${CC:-cc} $(CFLAGS_ZI) $$(find build/tests/lessons-c -type d -printf ' -iquote %p') $$(find build/tests/lessons-c -name '*.c') \
		build/ziran/libziran.a -Wl,--gc-sections -lm -lpthread -o $@

build/tests/dino: tests/dino_test.zi $(wildcard src/*.zi) build/ziran/libziran.a
	rm -rf build/tests/dino-c
	'$(ZIRANC)' build --target=c --root . --module-path 'std=$(TOOLCHAIN)/std' --module-path '$(TOOLCHAIN)/std' \
		--entry dino_test:main -o build/tests/dino-c tests/dino_test.zi
	$${CC:-cc} $(CFLAGS_ZI) $$(find build/tests/dino-c -type d -printf ' -iquote %p') $$(find build/tests/dino-c -name '*.c') \
		build/ziran/libziran.a -Wl,--gc-sections -lm -lpthread -o $@

# Sound effects: tools/sounds.zi into assets/sounds (committed).
sounds: build/tools/sounds
	build/tools/sounds

build/tools/sounds: tools/sounds.zi build/ziran/libziran.a
	rm -rf build/tools/sounds-c
	'$(ZIRANC)' build --target=c --root tools --module-path 'std=$(TOOLCHAIN)/std' --module-path '$(TOOLCHAIN)/std' \
		--entry sounds:main -o build/tools/sounds-c tools/sounds.zi
	$${CC:-cc} $(CFLAGS_ZI) $$(find build/tools/sounds-c -type d -printf ' -iquote %p') $$(find build/tools/sounds-c -name '*.c') \
		build/ziran/libziran.a -Wl,--gc-sections -lm -lpthread -o $@

BIN_DIR ?= $(HOME)/.local/bin
LIB_DIR ?= $(HOME)/.local/lib/jungle
DATA_DIR ?= $(if $(XDG_DATA_HOME),$(XDG_DATA_HOME),$(HOME)/.local/share)

.PHONY: install
# The program finds assets/ beside itself.
install: build/jungle
	mkdir -p '$(LIB_DIR)/assets' '$(BIN_DIR)' '$(DATA_DIR)/applications' '$(DATA_DIR)/icons/hicolor/256x256/apps'
	cp -r assets/. '$(LIB_DIR)/assets/'
	install -m 0755 build/jungle '$(LIB_DIR)/jungle.new'
	mv -f '$(LIB_DIR)/jungle.new' '$(LIB_DIR)/jungle'
	ln -sfn '$(LIB_DIR)/jungle' '$(BIN_DIR)/jungle'
	install -m 0644 assets/icon.png '$(DATA_DIR)/icons/hicolor/256x256/apps/xyz.waozi.jungle.png'
	install -m 0644 packaging/xyz.waozi.jungle.desktop '$(DATA_DIR)/applications/'
