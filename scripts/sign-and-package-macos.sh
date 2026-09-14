#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-${PROJECT_DIR}/build-macos}"
CONFIG="${CONFIG:-Release}"
VERSION_OVERRIDE="${VERSION:-}"
BUILD_NUMBER="${BUILD_NUMBER:-${GITHUB_RUN_NUMBER:-}}"
APP_SIGN_IDENTITY="${APP_SIGN_IDENTITY:--}"
INSTALLER_SIGN_IDENTITY="${INSTALLER_SIGN_IDENTITY:-}"
NOTARY_PROFILE="${NOTARY_PROFILE:-}"
COMMERCIAL_RELEASE="${COMMERCIAL_RELEASE:-0}"
ARTIFACT_DIR="${BUILD_DIR}/Septum_artefacts/${CONFIG}"
DIST_DIR="${BUILD_DIR}/dist"
PACKAGE_ROOT="${BUILD_DIR}/package-root"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "error: this script requires macOS" >&2
    exit 1
fi

if [[ ! "${BUILD_NUMBER}" =~ ^[0-9]+$ ]]; then
    echo "error: set BUILD_NUMBER to a numeric build number (or run in GitHub Actions)" >&2
    exit 1
fi

# Fail before touching prior staging or release artifacts. CI can continue
# making ad-hoc packages, while commercial runs must complete notarization.
if [[ "${COMMERCIAL_RELEASE}" != "0" && "${COMMERCIAL_RELEASE}" != "1" ]]; then
    echo "error: COMMERCIAL_RELEASE must be 0 or 1" >&2
    exit 1
fi
if [[ "${COMMERCIAL_RELEASE}" == "1" && -z "${NOTARY_PROFILE}" ]]; then
    echo "error: COMMERCIAL_RELEASE=1 requires NOTARY_PROFILE" >&2
    exit 1
fi
if [[ -n "${NOTARY_PROFILE}" ]]; then
    if [[ "${APP_SIGN_IDENTITY}" == "-" || -z "${INSTALLER_SIGN_IDENTITY}" \
          || "${INSTALLER_SIGN_IDENTITY}" == "-" ]]; then
        echo "error: notarization requires Developer ID Application and Installer identities" >&2
        exit 1
    fi
fi

required_tools=(codesign ditto lipo pkgbuild mktemp)
if [[ -n "${INSTALLER_SIGN_IDENTITY}" ]]; then
    required_tools+=(productsign)
fi
if [[ -n "${NOTARY_PROFILE}" ]]; then
    required_tools+=(xcrun)
fi
for tool in "${required_tools[@]}"; do
    command -v "${tool}" >/dev/null 2>&1 || {
        echo "error: required tool '${tool}' was not found" >&2
        exit 1
    }
done
if [[ -n "${NOTARY_PROFILE}" ]]; then
    xcrun --find notarytool >/dev/null
    xcrun --find stapler >/dev/null
fi

JUCE_NOTICE="${PROJECT_DIR}/ThirdParty/JUCE-LICENSE.md"
JUCE_DEPENDENCIES="${PROJECT_DIR}/ThirdParty/JUCE-DEPENDENCY-NOTICES.txt"
for notice in "${PROJECT_DIR}/LICENSE" "${PROJECT_DIR}/THIRD_PARTY_NOTICES.md" \
              "${JUCE_NOTICE}" "${JUCE_DEPENDENCIES}"; do
    if [[ ! -f "${notice}" ]]; then
        echo "error: missing distribution notice: ${notice}" >&2
        exit 1
    fi
done

VST3="${ARTIFACT_DIR}/VST3/Septum.vst3"
AU="${ARTIFACT_DIR}/AU/Septum.component"
APP="${ARTIFACT_DIR}/Standalone/Septum.app"

for artifact in "${VST3}" "${AU}" "${APP}"; do
    if [[ ! -d "${artifact}" ]]; then
        echo "error: missing build artifact: ${artifact}" >&2
        echo "Run scripts/build-macos.sh first." >&2
        exit 1
    fi
done

PLIST_BUDDY="${PLIST_BUDDY:-/usr/libexec/PlistBuddy}"
if [[ ! -x "${PLIST_BUDDY}" ]]; then
    echo "error: PlistBuddy was not found" >&2
    exit 1
fi

bundle_version() {
    "${PLIST_BUDDY}" -c "Print :CFBundleShortVersionString" \
        "$1/Contents/Info.plist"
}

VST3_VERSION="$(bundle_version "${VST3}")"
AU_VERSION="$(bundle_version "${AU}")"
APP_VERSION="$(bundle_version "${APP}")"
if [[ -z "${VST3_VERSION}" || "${VST3_VERSION}" != "${AU_VERSION}" \
      || "${VST3_VERSION}" != "${APP_VERSION}" ]]; then
    echo "error: build artifact versions disagree" >&2
    echo "  VST3: ${VST3_VERSION:-missing}" >&2
    echo "  AU: ${AU_VERSION:-missing}" >&2
    echo "  App: ${APP_VERSION:-missing}" >&2
    exit 1
fi

VERSION="${VST3_VERSION}"
if [[ -n "${VERSION_OVERRIDE}" && "${VERSION_OVERRIDE}" != "${VERSION}" ]]; then
    echo "error: VERSION=${VERSION_OVERRIDE} does not match bundle version ${VERSION}" >&2
    exit 1
fi

VST3_ARCHS="$(lipo -archs "${VST3}/Contents/MacOS/Septum")"
AU_ARCHS="$(lipo -archs "${AU}/Contents/MacOS/Septum")"
APP_ARCHS="$(lipo -archs "${APP}/Contents/MacOS/Septum")"
if [[ "${VST3_ARCHS}" != "${AU_ARCHS}" || "${VST3_ARCHS}" != "${APP_ARCHS}" ]]; then
    echo "error: build artifact architectures disagree" >&2
    echo "  VST3: ${VST3_ARCHS}" >&2
    echo "  AU: ${AU_ARCHS}" >&2
    echo "  App: ${APP_ARCHS}" >&2
    exit 1
fi

if [[ "${APP_ARCHS}" == *arm64* && "${APP_ARCHS}" == *x86_64* ]]; then
    ARTIFACT_ARCH="universal"
else
    ARTIFACT_ARCH="${APP_ARCHS// /-}"
fi

if [[ -n "${NOTARY_PROFILE}" ]]; then
    for artifact in "${VST3}" "${AU}" "${APP}"; do
        bundle_type="$("${PLIST_BUDDY}" -c "Print :CFBundlePackageType" \
            "${artifact}/Contents/Info.plist")"
        if [[ "${bundle_type}" != "BNDL" && "${bundle_type}" != "APPL" ]]; then
            echo "error: notarization requires a recognised executable bundle: ${artifact}" >&2
            exit 1
        fi
    done
fi

case "${PACKAGE_ROOT}" in
    "${BUILD_DIR}"/*) ;;
    *) echo "error: unsafe package staging path: ${PACKAGE_ROOT}" >&2; exit 1 ;;
esac

rm -rf "${PACKAGE_ROOT}"
mkdir -p \
    "${PACKAGE_ROOT}/Library/Audio/Plug-Ins/VST3" \
    "${PACKAGE_ROOT}/Library/Audio/Plug-Ins/Components" \
    "${PACKAGE_ROOT}/Applications" \
    "${DIST_DIR}"

ditto "${VST3}" "${PACKAGE_ROOT}/Library/Audio/Plug-Ins/VST3/Septum.vst3"
ditto "${AU}" "${PACKAGE_ROOT}/Library/Audio/Plug-Ins/Components/Septum.component"
ditto "${APP}" "${PACKAGE_ROOT}/Applications/Septum.app"

NOTICE_ROOT="${PACKAGE_ROOT}/Library/Application Support/Septum/Documentation"

mkdir -p "${NOTICE_ROOT}"
ditto "${PROJECT_DIR}/LICENSE" "${NOTICE_ROOT}/Septum-LICENSE.txt"
ditto "${PROJECT_DIR}/THIRD_PARTY_NOTICES.md" \
    "${NOTICE_ROOT}/THIRD_PARTY_NOTICES.md"
ditto "${JUCE_NOTICE}" "${NOTICE_ROOT}/JUCE-LICENSE.md"
ditto "${JUCE_DEPENDENCIES}" "${NOTICE_ROOT}/JUCE-DEPENDENCY-NOTICES.txt"

# Keep the same notices inside every independently copyable bundle. They are
# installed before signing so the bundle signatures cover the documentation.
for bundle in \
    "${PACKAGE_ROOT}/Library/Audio/Plug-Ins/VST3/Septum.vst3" \
    "${PACKAGE_ROOT}/Library/Audio/Plug-Ins/Components/Septum.component" \
    "${PACKAGE_ROOT}/Applications/Septum.app"; do
    bundle_notice_root="${bundle}/Contents/Resources/Documentation"
    mkdir -p "${bundle_notice_root}"
    ditto "${PROJECT_DIR}/LICENSE" "${bundle_notice_root}/Septum-LICENSE.txt"
    ditto "${PROJECT_DIR}/THIRD_PARTY_NOTICES.md" \
        "${bundle_notice_root}/THIRD_PARTY_NOTICES.md"
    ditto "${JUCE_NOTICE}" "${bundle_notice_root}/JUCE-LICENSE.md"
    ditto "${JUCE_DEPENDENCIES}" "${bundle_notice_root}/JUCE-DEPENDENCY-NOTICES.txt"
done

sign_bundle() {
    local bundle="$1"
    if [[ "${APP_SIGN_IDENTITY}" == "-" ]]; then
        codesign --force --sign - "${bundle}"
    else
        codesign --force --options runtime --timestamp \
            --sign "${APP_SIGN_IDENTITY}" "${bundle}"
    fi
    codesign --verify --deep --strict --verbose=2 "${bundle}"
}

sign_bundle "${PACKAGE_ROOT}/Library/Audio/Plug-Ins/VST3/Septum.vst3"
sign_bundle "${PACKAGE_ROOT}/Library/Audio/Plug-Ins/Components/Septum.component"
sign_bundle "${PACKAGE_ROOT}/Applications/Septum.app"

# Build the entire new release away from dist. A signing/notarization failure
# must leave the last successful distributables intact.
RELEASE_WORK_DIR="$(mktemp -d "${BUILD_DIR}/package-release.XXXXXX")"
trap 'rm -rf "${RELEASE_WORK_DIR}"' EXIT
ZIP_NAME="Septum-${VERSION}-build-${BUILD_NUMBER}-macOS-${ARTIFACT_ARCH}.zip"
PKG_NAME="Septum-${VERSION}-build-${BUILD_NUMBER}-macOS-${ARTIFACT_ARCH}.pkg"
ZIP_PATH="${RELEASE_WORK_DIR}/${ZIP_NAME}"
PKG_UNSIGNED="${RELEASE_WORK_DIR}/unsigned.pkg"
PKG_FINAL="${RELEASE_WORK_DIR}/${PKG_NAME}"

make_zip() {
    # Omit machine-local metadata; preserve the signed bundle contents and
    # notarization tickets stored inside them.
    ditto -c -k --norsrc --noextattr --noqtn --noacl \
        "${PACKAGE_ROOT}" "${ZIP_PATH}"
}

notarize() {
    local archive="$1"
    local result="${RELEASE_WORK_DIR}/notary-result.plist"
    xcrun notarytool submit "${archive}" \
        --keychain-profile "${NOTARY_PROFILE}" --wait --output-format plist > "${result}"
    local status
    status="$("${PLIST_BUDDY}" -c "Print :status" "${result}")"
    if [[ "${status}" != "Accepted" ]]; then
        echo "error: notarization did not accept ${archive##*/}: ${status}" >&2
        cat "${result}" >&2
        exit 1
    fi
}

if [[ -n "${NOTARY_PROFILE}" ]]; then
    # Apple notarizes executable bundles in a ZIP but the ZIP itself cannot
    # carry a ticket. Staple each APPL/BNDL before producing the final ZIP and
    # installer. Both JUCE plug-in formats declare CFBundlePackageType=BNDL.
    # https://developer.apple.com/documentation/security/customizing-the-notarization-workflow
    make_zip
    notarize "${ZIP_PATH}"
    for bundle in \
        "${PACKAGE_ROOT}/Library/Audio/Plug-Ins/VST3/Septum.vst3" \
        "${PACKAGE_ROOT}/Library/Audio/Plug-Ins/Components/Septum.component" \
        "${PACKAGE_ROOT}/Applications/Septum.app"; do
        xcrun stapler staple "${bundle}"
        xcrun stapler validate "${bundle}"
        codesign --verify --deep --strict --verbose=2 "${bundle}"
    done
    rm -f "${ZIP_PATH}"
fi

COPYFILE_DISABLE=1 pkgbuild \
    --root "${PACKAGE_ROOT}" \
    --identifier cz.protocodus.septum.pkg \
    --version "${VERSION}" \
    --install-location / \
    "${PKG_UNSIGNED}"

if [[ -n "${INSTALLER_SIGN_IDENTITY}" ]]; then
    productsign --sign "${INSTALLER_SIGN_IDENTITY}" \
        "${PKG_UNSIGNED}" "${PKG_FINAL}"
    rm -f "${PKG_UNSIGNED}"
else
    mv "${PKG_UNSIGNED}" "${PKG_FINAL}"
fi

make_zip
if [[ -n "${NOTARY_PROFILE}" ]]; then
    # Validate the actual ZIP contents after extraction, including its tickets.
    # This catches archive options accidentally dropping signing metadata.
    ZIP_CHECK_ROOT="${RELEASE_WORK_DIR}/zip-validation"
    ditto -x -k "${ZIP_PATH}" "${ZIP_CHECK_ROOT}"
    for relative_bundle in "Library/Audio/Plug-Ins/VST3/Septum.vst3" \
                           "Library/Audio/Plug-Ins/Components/Septum.component" \
                           "Applications/Septum.app"; do
        codesign --verify --deep --strict --verbose=2 "${ZIP_CHECK_ROOT}/${relative_bundle}"
        xcrun stapler validate "${ZIP_CHECK_ROOT}/${relative_bundle}"
    done
    notarize "${PKG_FINAL}"
    xcrun stapler staple "${PKG_FINAL}"
    xcrun stapler validate "${PKG_FINAL}"
fi

# Replace previous release names only after every required stage succeeds.
# Moves stay on the build filesystem so no partial archive is copied to dist.
mv -f "${ZIP_PATH}" "${DIST_DIR}/${ZIP_NAME}"
mv -f "${PKG_FINAL}" "${DIST_DIR}/${PKG_NAME}"
for old in "${DIST_DIR}/Septum-"*-macOS-*.zip \
           "${DIST_DIR}/Septum-"*-macOS-*.pkg \
           "${DIST_DIR}/Septum-"*-unsigned.pkg; do
    if [[ "${old}" != "${DIST_DIR}/${ZIP_NAME}" && "${old}" != "${DIST_DIR}/${PKG_NAME}" ]]; then
        rm -f "${old}"
    fi
done

echo
echo "Packaging complete:"
echo "  ${DIST_DIR}/${ZIP_NAME}"
echo "  ${DIST_DIR}/${PKG_NAME}"
