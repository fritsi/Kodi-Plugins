set -euo pipefail

WORKING_DIR="$HOME/tmp/Kodi"

cd "$WORKING_DIR"

####################################################################################################

git clone https://github.com/xbmc/xbmc
git clone https://github.com/kodi-pvr/pvr.iptvsimple
git clone git@github.com:fritsi/kodi-pvr.git pvr.fritsi

(cd "$WORKING_DIR/xbmc" && git checkout 19.5-Matrix -b 19.5-Matrix)
(cd "$WORKING_DIR/pvr.iptvsimple" && git checkout Matrix)
(cd "$WORKING_DIR/pvr.fritsi" && git checkout 19.2.2-Matrix)

####################################################################################################

cd "$WORKING_DIR/xbmc/tools/depends"
./bootstrap
./configure --host=x86_64-apple-darwin --with-platform=macos
make -j6

####################################################################################################

cd "$WORKING_DIR/xbmc"
make -j6 -C tools/depends/target/binary-addons "ADDONS=pvr.iptvsimple" "ADDON_SRC_PREFIX=$WORKING_DIR"

####################################################################################################

cd "$WORKING_DIR/xbmc"

mkdir -p cmake/addons/addons/pvr.fritsi
echo "all" > cmake/addons/addons/pvr.fritsi/platforms.txt
echo "pvr.fritsi https://github.com/fritsi/kodi-pvr.git 19.2.2-Matrix" > cmake/addons/addons/pvr.fritsi/pvr.fritsi.txt

make -j6 -C tools/depends/target/binary-addons "ADDONS=pvr.fritsi" "ADDON_SRC_PREFIX=$WORKING_DIR"

####################################################################################################

cd "$WORKING_DIR/xbmc"
make -C tools/depends/target/cmakebuildsys
make -j6 -C build

####################################################################################################

mkdir "$WORKING_DIR/Xcode-build"
cd "$WORKING_DIR/xbmc"
make -C tools/depends/target/cmakebuildsys "BUILD_DIR=$WORKING_DIR/Xcode-build" "GEN=Xcode"

####################################################################################################

XBMC_CMAKE="/Users/Shared/xbmc-depends/x86_64-darwin20.6.0-native/bin/cmake"
TOOLCHAIN_FILE="/Users/Shared/xbmc-depends/macosx12.1_x86_64-target-debug/share/Toolchain.cmake"

mkdir "$WORKING_DIR/Xcode-build"
cd "$WORKING_DIR/Xcode-build"
"$XBMC_CMAKE" -G Xcode "-DCMAKE_TOOLCHAIN_FILE=$TOOLCHAIN_FILE" ../xbmc
