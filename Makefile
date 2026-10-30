.DEFAULT_GOAL := all
ZIRAN ?= ziran
LOCK_FLAGS := $(if $(wildcard ziran.local.toml),,--locked)
TOOLCHAIN = $(shell $(ZIRAN) pkg path ziran $(LOCK_FLAGS))
KRYON = $(shell $(ZIRAN) pkg path kryon $(LOCK_FLAGS))
MINGCUTE = $(shell $(ZIRAN) pkg path mingcute $(LOCK_FLAGS))
ZIRANC = $(TOOLCHAIN)/build/bin/ziran
MODULES = --module-path '$(KRYON)/src/ui' --module-path '$(KRYON)/src/backend' \
	--module-path 'kryon=$(KRYON)/src/ui' --module-path 'kryon=$(KRYON)/src/backend' \
	--module-path 'mingcute=$(MINGCUTE)/src' \
	--module-path 'std=$(TOOLCHAIN)/std' --module-path '$(TOOLCHAIN)/std'
# Speech clips are Ogg Vorbis (host/sound.zi DecodeSpeech). The versioned name
# links the runtime library without its development package.
DESKTOP_LIBS = $$(pkg-config --libs sdl2 cairo freetype2 fontconfig pangocairo) -l:libvorbisfile.so.3 -ldl -lm -lpthread
CFLAGS_ZI = -std=c11 -O2 -ffunction-sections -fdata-sections -I'$(TOOLCHAIN)/include'
# The app as it is installed: the program, its menu assets and the games.
APP := build/app
# Installed shared assets, their manifest and each game's staged bundle files.
SHARED := $(APP)/assets/shared-assets.txt $(APP)/assets/speech.txt
STAGED_GAMES := jungle-book jungle-abc jungle-numbers animal-count dino-paint jungle-shapes jungle-hide-seek jungle-drums jungle-garden
# Folders too: removing a file changes its folder's time, so staging reruns.
SHARED_SOURCES := $(shell find assets/jungle assets/jungle-book $(addprefix assets/,abc numbers animal-count dino-paint shapes hide_seek drums garden) 2>/dev/null)
GAMES := $(APP)/games/jungle-book.zx $(APP)/games/jungle-abc.zx $(APP)/games/jungle-numbers.zx $(APP)/games/animal-count.zx $(APP)/games/dino-paint.zx $(APP)/games/jungle-jigsaw.zx $(APP)/games/jungle-piano.zx
KRYON_SOURCES = $(wildcard $(KRYON)/src/ui/*.zi $(KRYON)/src/backend/*.zi)

# A package update can change hosted widget records as well as rendering.
# Rebuild the host and bundles together instead of mixing their layouts.
$(APP)/jungle $(GAMES): ziran.lock $(KRYON_SOURCES)

.PHONY: all run art sounds test test-ui install locales web

web:
	python3 tools/build_web.py

locales:
	python3 tools/locales.py

all: $(APP)/jungle $(GAMES) $(APP)/games/catalog.txt $(SHARED)

run: all
	$(APP)/jungle

build/ziran/libziran.a:
	$(MAKE) -C '$(TOOLCHAIN)' BUILD_DIR='$(abspath build/ziran)' '$(abspath $@)'

$(APP)/jungle: $(wildcard host/*.zi retro/*.zi games/paint/paint_palette.zi games/paint/paint_picture.zi) build/ziran/libziran.a
	mkdir -p $(APP)
	@set -eu; output=$$(mktemp -d build/host-c.XXXXXX); \
		trap 'rm -rf "$$output"' EXIT; \
		'$(ZIRANC)' build --target=c --root host $(MODULES) --entry desktop:main -o "$$output" host/desktop.zi; \
		$${CC:-cc} $(CFLAGS_ZI) $$(find "$$output" -type d -printf ' -iquote %p') $$(find "$$output" -name '*.c') \
		build/ziran/libziran.a -Wl,--gc-sections $(DESKTOP_LIBS) -o "$$output/jungle"; \
		mv "$$output/jungle" $@

$(APP)/games/catalog.txt: games/catalog.txt
	mkdir -p $(APP)/games
	cp $< $@

# Picture Book artwork, fonts and identical pictures ship once, installed
# beside the app; the manifest names them for every host. Narration ships
# once too, as Ogg Vorbis speech clips (needs ffmpeg with libvorbis) that
# assets/speech.txt composes into every narration path. Each game's bundle
# carries only its own pictures and effects. Staging synchronizes every
# folder, so assets removed from assets/ leave the app and bundles too.
# The manifest and each GAME.files listing change only when their contents
# do, so an unrelated asset change rebuilds no bundle.
build/stage/.shared-assets: tools/shared_assets.py tools/speech_manifest.py tools/speech_codec.py tools/book_speech.py tools/book_catalog.py $(SHARED_SOURCES)
	python3 tools/shared_assets.py

$(SHARED) $(addprefix build/stage/,$(addsuffix .files,$(STAGED_GAMES))): build/stage/.shared-assets
	@test -e $@ || python3 tools/shared_assets.py

$(APP)/games/jungle-book.zx: $(wildcard games/book/*.zi retro/*.zi) build/stage/jungle-book.files
	mkdir -p $(APP)/games
	'$(ZIRANC)' bundle --root games/book $(MODULES) --define KRYON_HOSTED_UI \
		--asset-dir assets=build/stage/jungle-book/assets --entry jungle_book:main -o $@ games/book/jungle_book.zi

# ABC Book draws the installed watercolor pictures and narration, so its
# bundle carries only its own quiet sounds and letters.
$(APP)/games/jungle-abc.zx: $(wildcard games/abc/*.zi retro/*.zi) build/stage/jungle-abc.files
	mkdir -p $(APP)/games
	'$(ZIRANC)' bundle --root games/abc $(MODULES) --define KRYON_HOSTED_UI \
		--asset-dir assets=build/stage/jungle-abc/assets --entry jungle_abc:main -o $@ games/abc/jungle_abc.zi

# 123 Book draws the installed watercolor pictures, so its bundle carries
# only its own quiet sounds and questions.
$(APP)/games/jungle-numbers.zx: $(wildcard games/numbers/*.zi retro/*.zi) build/stage/jungle-numbers.files
	mkdir -p $(APP)/games
	'$(ZIRANC)' bundle --root games/numbers $(MODULES) --define KRYON_HOSTED_UI \
		--asset-dir assets=build/stage/jungle-numbers/assets --entry jungle_numbers:main -o $@ games/numbers/jungle_numbers.zi

# Animal Counting draws the installed counting pictures through aliases.
$(APP)/games/animal-count.zx: $(wildcard games/animal/*.zi retro/*.zi) build/stage/animal-count.files
	mkdir -p $(APP)/games
	'$(ZIRANC)' bundle --root games/animal $(MODULES) --define KRYON_HOSTED_UI \
		--asset-dir assets=build/stage/animal-count/assets --entry animal_count:main -o $@ games/animal/animal_count.zi

$(APP)/games/dino-paint.zx: $(wildcard games/paint/*.zi retro/*.zi) build/stage/dino-paint.files
	mkdir -p $(APP)/games
	'$(ZIRANC)' bundle --root games/paint $(MODULES) --define KRYON_HOSTED_UI \
		--asset-dir assets=build/stage/dino-paint/assets --entry dino_paint:main -o $@ games/paint/dino_paint.zi

# One score and the same pitched samples, shared by every piano host.
$(APP)/games/jungle-piano.zx: $(wildcard games/piano/*.zi retro/*.zi) $(wildcard assets/piano/sounds/*.wav)
	mkdir -p $(APP)/games
	'$(ZIRANC)' bundle --root games/piano $(MODULES) --define KRYON_HOSTED_UI \
		--asset-dir assets/piano=assets/piano --entry jungle_piano:main -o $@ games/piano/jungle_piano.zi

# Full pictures only: every host clips its own interlocking puzzle pieces.
$(APP)/games/jungle-jigsaw.zx: $(wildcard games/jigsaw/*.zi retro/*.zi) $(shell find assets/jigsaw -type f)
	mkdir -p $(APP)/games
	'$(ZIRANC)' bundle --root games/jigsaw $(MODULES) --define KRYON_HOSTED_UI \
		--asset-dir assets/jigsaw=assets/jigsaw --entry jungle_jigsaw:main -o $@ games/jigsaw/jungle_jigsaw.zi

# Menu pixel art from SVG, Picture Book raster cartoons, then Dino Colors'
# vector art traced from its generated sheets and compiled into masks.
# games/paint/paint_pages.zi and its pictures are committed, so a fresh
# checkout's file times never make an ordinary build regenerate them.
art: build/tools/art
	build/tools/art
	python3 tools/book_art.py
	python3 tools/counting_art.py
	python3 tools/menu_art.py
	python3 tools/branding.py
	python3 tools/dino_art.py
	python3 tools/paint_scenes.py
	python3 tools/paint_pages.py

# Sound effects into assets/ (committed).
sounds: build/tools/sounds
	build/tools/sounds
	python3 tools/piano_sounds.py

build/tools/%: tools/%.zi $(wildcard tools/*.zi) build/ziran/libziran.a
	rm -rf build/tools/$*-c
	'$(ZIRANC)' build --target=c --root tools --module-path 'std=$(TOOLCHAIN)/std' --module-path '$(TOOLCHAIN)/std' \
		--entry $*:main -o build/tools/$*-c $<
	$${CC:-cc} $(CFLAGS_ZI) $$(find build/tools/$*-c -type d -printf ' -iquote %p') $$(find build/tools/$*-c -name '*.c') \
		build/ziran/libziran.a -Wl,--gc-sections -lm -lpthread $(TEST_LIBS) -o $@

build/tests/voice build/tests/speech_codec: TEST_LIBS = $(DESKTOP_LIBS)

build/tests/%: tests/%_test.zi $(wildcard games/*/*.zi host/*.zi retro/*.zi) build/ziran/libziran.a
	rm -rf build/tests/$*-c
	'$(ZIRANC)' build --target=c --root tests $(MODULES) \
		--entry $*_test:main -o build/tests/$*-c $<
	$${CC:-cc} $(CFLAGS_ZI) $$(find build/tests/$*-c -type d -printf ' -iquote %p') $$(find build/tests/$*-c -name '*.c') \
		build/ziran/libziran.a -Wl,--gc-sections -lm -lpthread $(TEST_LIBS) -o $@

# Questions, painting and PNG pictures, then every game opened in the app.
test: build/tests/paint build/tests/png build/tests/progress build/tests/document build/tests/counting build/tests/abc build/tests/numbers build/tests/printing build/tests/audio build/tests/voice build/tests/book_preferences build/tests/jigsaw build/tests/piano all
	build/tests/piano
	python3 tests/piano_audio_test.py
	build/tests/jigsaw
	build/tests/paint
	build/tests/progress
	build/tests/document
	build/tests/counting
	build/tests/abc
	build/tests/numbers
	build/tests/audio
	build/tests/book_preferences
	cd $(APP) && SDL_AUDIODRIVER=dummy ../tests/voice
	build/tests/png build/tests/check.png
	test "$$(convert build/tests/check.png -format '%w %h %[pixel:p{0,0}] %[pixel:p{2,1}]' info:)" = "3 2 srgb(170,0,0) srgb(255,255,85)"
	rm -rf build/tests/data
	mkdir -p build/tests/data
	printf 'jungle 1\nfruits 4\n' > build/tests/data/progress.txt
	JUNGLE_DATA=$(abspath build/tests/data) $(APP)/jungle --check
	python3 tests/runtime_test.py
	python3 tests/paint_choices_ui_test.py
	python3 tests/export_test.py
	python3 tests/assets_test.py
	python3 tests/shared_assets_test.py
	python3 tests/speech_manifest_test.py
	python3 tests/speech_codec_test.py
	python3 tests/speech_playback_test.py
	python3 tests/language_test.py
	python3 tests/abc_audio_test.py
	python3 tests/numbers_audio_test.py
	python3 tests/jigsaw_art_test.py
	python3 tests/brand_metadata_test.py
	python3 tests/asset_packs_test.py
	python3 tests/android_editions_test.py

# Actual input and rendering on a private display; requires Xvfb, xdotool,
# ImageMagick and Pillow. Never uses the inherited desktop or owner saves.
test-ui: all
	python3 tests/piano_ui_test.py
	python3 tests/menu_ui_test.py
	python3 tests/jigsaw_ui_test.py
	python3 tests/runtime_test.py --ui
	python3 tests/book_ui_test.py
	python3 tests/book_additions_ui_test.py
	python3 tests/learning_menu_test.py
	python3 tests/abc_sequence_ui_test.py
	python3 tests/playback_ui_test.py
	python3 tests/slot_preview_test.py
	python3 tests/language_ui_test.py

BIN_DIR ?= $(HOME)/.local/bin
LIB_DIR ?= $(HOME)/.local/lib/jungle
DATA_DIR ?= $(if $(XDG_DATA_HOME),$(XDG_DATA_HOME),$(HOME)/.local/share)

# The program finds assets/ and games/ beside itself.
install: all
	mkdir -p '$(LIB_DIR)' '$(BIN_DIR)' '$(DATA_DIR)/applications' '$(DATA_DIR)/icons/hicolor/64x64/apps'
	@# Replace the app's own assets/ and games/ whole, so removed files do not
	@# linger; saves live in the data folder and are never touched.
	rm -rf '$(LIB_DIR)/assets.new' '$(LIB_DIR)/games.new' '$(LIB_DIR)/assets.old' '$(LIB_DIR)/games.old'
	cp -r $(APP)/assets '$(LIB_DIR)/assets.new'
	mkdir '$(LIB_DIR)/games.new'
	cp $(APP)/games/*.zx $(APP)/games/catalog.txt '$(LIB_DIR)/games.new/'
	@for folder in assets games; do \
		if [ -e '$(LIB_DIR)/'$$folder ]; then mv '$(LIB_DIR)/'$$folder '$(LIB_DIR)/'$$folder.old; fi; \
		mv '$(LIB_DIR)/'$$folder.new '$(LIB_DIR)/'$$folder; \
		rm -rf '$(LIB_DIR)/'$$folder.old; \
	done
	install -m 0755 $(APP)/jungle '$(LIB_DIR)/jungle.new'
	mv -f '$(LIB_DIR)/jungle.new' '$(LIB_DIR)/jungle'
	ln -sfn '$(LIB_DIR)/jungle' '$(BIN_DIR)/jungle'
	@for size in 16 32 48 64 128 256 512; do \
		mkdir -p '$(DATA_DIR)/icons/hicolor/'$$size'x'$$size'/apps'; \
		install -m 0644 assets/jungle/icons/icon-$$size.png '$(DATA_DIR)/icons/hicolor/'$$size'x'$$size'/apps/xyz.waozi.jungle.png'; \
	done
	mkdir -p '$(DATA_DIR)/metainfo'
	install -m 0644 packaging/xyz.waozi.jungle.metainfo.xml '$(DATA_DIR)/metainfo/'
	python3 tools/install_desktop.py '$(LIB_DIR)' '$(DATA_DIR)'
