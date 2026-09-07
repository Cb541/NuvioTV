#!/usr/bin/env python3

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "NuvioMobile"


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def find_file(name, contains=None):
    hits = []

    for p in SRC.rglob(name):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue

        if contains is None or contains in text:
            hits.append(p)

    if not hits:
        fail(f"could not find {name}")

    if len(hits) > 1:
        print(f"WARN: multiple {name} files found; using {hits[0]}")

    return hits[0]


def write_if_changed(path, original, updated, label):
    if updated == original:
        print(f"{label}: already patched")
        return False

    path.write_text(updated, encoding="utf-8")
    print(f"{label}: patched")
    return True


# ---------------------------------------------------------------------------
# Shared Kotlin profile model
# ---------------------------------------------------------------------------

def patch_models():
    path = SRC / (
        "shared/src/commonMain/kotlin/"
        "com/nuvio/app/features/profiles/ProfileModels.kt"
    )

    if not path.exists():
        fail(f"missing {path}")

    text = path.read_text(encoding="utf-8")
    original = text

    # NuvioProfile
    profile_marker = (
        '    @SerialName("avatar_url") val avatarUrl: String? = null,'
    )

    if "backgroundUrl: String?" not in text:
        if profile_marker not in text:
            fail("could not find NuvioProfile avatar_url field")

        text = text.replace(
            profile_marker,
            profile_marker
            + '\n'
            + '    @SerialName("background_url") '
              'val backgroundUrl: String? = null,',
            1,
        )

    # ProfilePushPayload
    payload_marker = (
        '    @SerialName("avatar_url") val avatarUrl: String? = null,'
    )

    if text.count("backgroundUrl: String?") < 2:
        matches = list(re.finditer(
            re.escape(payload_marker),
            text
        ))

        if len(matches) < 2:
            fail(
                "could not locate both avatar_url fields required for "
                "NuvioProfile and ProfilePushPayload"
            )

        # Insert after the second avatar_url declaration.
        second = matches[1]

        insert_at = second.end()

        text = (
            text[:insert_at]
            + '\n'
              '    @SerialName("background_url") '
              'val backgroundUrl: String? = null,'
            + text[insert_at:]
        )

    # Helper used from Swift through SharedCore.
    if "fun normalizedProfileBackgroundUrl" not in text:
        helper = r'''

fun normalizedProfileBackgroundUrl(url: String?): String? =
    url?.trim()?.takeIf { it.isValidProfileBackgroundUrl() }

private fun String.isValidProfileBackgroundUrl(): Boolean {
    val value = trim()

    if (value.length > 2048) return false
    if (value.any { it.isWhitespace() }) return false

    return value.startsWith("https://") ||
        value.startsWith("http://")
}

fun profileBackgroundImageUrl(profile: NuvioProfile): String? =
    normalizedProfileBackgroundUrl(profile.backgroundUrl)
'''

        # Add helpers at EOF, safely outside the data classes.
        text = text.rstrip() + helper + "\n"

    write_if_changed(path, original, text, "models")


# ---------------------------------------------------------------------------
# Shared Kotlin profile repository
# ---------------------------------------------------------------------------

def patch_repository():
    path = SRC / (
        "shared/src/commonMain/kotlin/"
        "com/nuvio/app/features/profiles/ProfileRepository.kt"
    )

    if not path.exists():
        fail(f"missing {path}")

    text = path.read_text(encoding="utf-8")
    original = text

    # Add backgroundUrl to createProfile and updateProfile signatures.
    for function_name in ("createProfile", "updateProfile"):
        if (
            re.search(
                rf"suspend\s+fun\s+{re.escape(function_name)}\s*\(",
                text
            )
            and "backgroundUrl:" not in text[
                max(
                    0,
                    text.find(f"fun {function_name}")
                ):
            ]
        ):
            pattern = re.compile(
                rf"(suspend\s+fun\s+{re.escape(function_name)}\s*\("
                rf".*?"
                rf"avatarUrl\s*:\s*String\?\s*=\s*null,)",
                re.S,
            )

            match = pattern.search(text)

            if match:
                replacement = (
                    match.group(1)
                    + "\n        backgroundUrl: String? = null,"
                )

                text = (
                    text[:match.start()]
                    + replacement
                    + text[match.end():]
                )

    # Add backgroundUrl to every ProfilePushPayload construction.
    #
    # Existing Beta 17 source has the same payload type used in create/update
    # and the local/offline path. We handle each construction independently.
    payload_pattern = re.compile(
        r"ProfilePushPayload\((.*?)\n\s*\)",
        re.S,
    )

    def patch_payload(match):
        block = match.group(0)

        if "backgroundUrl =" in block:
            return block

        # Existing payload from a profile:
        # avatarUrl = profile.avatarUrl
        if "avatarUrl = profile.avatarUrl" in block:
            return block.replace(
                "avatarUrl = profile.avatarUrl,",
                "avatarUrl = profile.avatarUrl,\n"
                "                backgroundUrl = profile.backgroundUrl,",
                1,
            )

        # Existing payload for the new/edited profile.
        #
        # createProfile/updateProfile use the local function parameter.
        if re.search(r"\bavatarUrl\s*=\s*avatarUrl,", block):
            return block.replace(
                "avatarUrl = avatarUrl,",
                "avatarUrl = avatarUrl,\n"
                "            backgroundUrl = backgroundUrl,",
                1,
            )

        return block

    patched_text = payload_pattern.sub(patch_payload, text)

    # The indentation can vary depending on which constructor we're handling;
    # do a second safe pass for payloads where the previous generic replacement
    # did not match because of indentation.
    text = patched_text

    # Local anonymous payload mapping should preserve backgroundUrl too.
    local_profile_pattern = (
        r"(NuvioProfile\(\s*"
        r".*?"
        r"avatarUrl\s*=\s*p\.avatarUrl,)"
    )

    if "backgroundUrl = p.backgroundUrl" not in text:
        text = re.sub(
            local_profile_pattern,
            r"\1\n                backgroundUrl = p.backgroundUrl,",
            text,
            count=1,
            flags=re.S,
        )

    # Make sure we actually touched the repository.
    if (
        "backgroundUrl" not in text
        and "background_url" not in text
    ):
        fail("repository patch made no changes")

    write_if_changed(path, original, text, "repository")


# ---------------------------------------------------------------------------
# tvOS ProfilesViewModel.swift
# ---------------------------------------------------------------------------

def patch_viewmodel():
    path = find_file(
        "ProfilesViewModel.swift",
        "class ProfilesViewModel",
    )

    text = path.read_text(encoding="utf-8")
    original = text

    # createProfile wrapper.
    create_pattern = re.compile(
        r"(func\s+createProfile\s*\("
        r".*?"
        r"avatarUrl\s*:\s*String\?,)",
        re.S,
    )

    if "backgroundUrl: String? = nil" not in text:
        match = create_pattern.search(text)

        if match:
            text = (
                text[:match.end()]
                + "\n        backgroundUrl: String? = nil,"
                + text[match.end():]
            )

    # updateProfile wrapper.
    update_pattern = re.compile(
        r"(func\s+updateProfile\s*\("
        r".*?"
        r"avatarUrl\s*:\s*String\?,)",
        re.S,
    )

    if text.count("backgroundUrl: String? = nil") < 2:
        match = update_pattern.search(text)

        if match:
            text = (
                text[:match.end()]
                + "\n        backgroundUrl: String? = nil,"
                + text[match.end():]
            )

    # Forward parameter to shared repository calls.
    if "backgroundUrl: backgroundUrl" not in text:
        text = text.replace(
            "avatarUrl: avatarUrl,\n",
            "avatarUrl: avatarUrl,\n"
            "            backgroundUrl: backgroundUrl,\n",
        )

    if text == original:
        print("viewmodel: already patched")
    else:
        print(
            "viewmodel: patched "
            f"({text.count('backgroundUrl: String? = nil')} signatures)"
        )
        path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Swift profile selection/editor
# ---------------------------------------------------------------------------

def patch_swift_view():
    path = SRC / "iosApp/NuvioTV/Screens/ProfileSelectionView.swift"

    if not path.exists():
        fail(f"missing {path}")

    text = path.read_text(encoding="utf-8")
    original = text

    # -----------------------------------------------------------------------
    # 1. Add the remote animated background behind the profile picker.
    # -----------------------------------------------------------------------

    if "ProfileSelectionRemoteAnimatedImage" not in text:
        marker = (
            "        ZStack {\n"
            "            Theme.Palette.background.ignoresSafeArea()"
        )

        replacement = """        ZStack {
            if let backgroundURL = profileSelectionBackgroundURL {
                ProfileSelectionRemoteAnimatedImage(urlString: backgroundURL)
                    .ignoresSafeArea()
            }

            Theme.Palette.background.ignoresSafeArea()"""

        if marker not in text:
            fail("could not find ProfileSelectionView background marker")

        text = text.replace(marker, replacement, 1)

    # Computed property for the currently selected/first profile.
    if "profileSelectionBackgroundURL" not in text:
        property_block = """    private var profileSelectionBackgroundURL: String? {
        let profile = model.activeProfile ?? model.profiles.first
        return profile.flatMap {
            ProfileModelsKt.profileBackgroundImageUrl(profile: $0)
        }
    }

"""

        body_marker = "    var body: some View {"

        if body_marker not in text:
            fail("could not find ProfileSelectionView body")

        text = text.replace(
            body_marker,
            property_block + body_marker,
            1,
        )

    # -----------------------------------------------------------------------
    # 2. Add state for the editable background URL.
    # -----------------------------------------------------------------------

    state_marker = "    @State private var avatarId: String?\n"

    if "@State private var backgroundUrl: String" not in text:
        if state_marker not in text:
            fail("could not find avatarId state declaration")

        text = text.replace(
            state_marker,
            state_marker
            + "    @State private var backgroundUrl: String\n",
            1,
        )

    # -----------------------------------------------------------------------
    # 3. Initialize it from the existing profile.
    # -----------------------------------------------------------------------

    init_marker = (
        "        _avatarId = State(initialValue: target.profile?.avatarId)\n"
    )

    if "_backgroundUrl = State(" not in text:
        if init_marker not in text:
            fail("could not find ProfileEditView avatarId initializer")

        text = text.replace(
            init_marker,
            init_marker
            + '        _backgroundUrl = State('
              'initialValue: target.profile?.backgroundUrl ?? "")\n',
            1,
        )

    # -----------------------------------------------------------------------
    # 4. Add the actual Background URL TextField after the Name field.
    #
    # Beta 17 uses:
    #
    #     TextField("Name", text: $name)
    #         .textFieldStyle(...)
    #
    # so we identify the complete block by the following Cloud avatar comment
    # instead of relying on a fragile exact indentation string.
    # -----------------------------------------------------------------------

    if 'TextField("Custom background URL"' not in text:
        name_start = text.find('TextField("Name", text: $name)')

        if name_start < 0:
            fail('could not find TextField("Name", text: $name)')

        cloud_marker = (
            "                     // Cloud avatar catalog"
        )

        cloud_pos = text.find(cloud_marker, name_start)

        if cloud_pos < 0:
            # Try the actual indentation currently used by Beta 17.
            cloud_marker = "// Cloud avatar catalog"
            cloud_pos = text.find(cloud_marker, name_start)

        if cloud_pos < 0:
            fail("could not find Cloud avatar catalog marker")

        # Locate the end of the Name field's modifiers by taking the text
        # immediately before the cloud catalog comment.
        prefix = text[:cloud_pos]

        # Insert the field immediately before the comment, preserving the
        # indentation used by the existing Swift source.
        field = """                     TextField("Custom background URL", text: $backgroundUrl)
                         .textFieldStyle(.plain)
                         .font(Theme.Font.body)
                         .foregroundStyle(Theme.Palette.textPrimary)
                         .padding(Theme.Spacing.lg)
                         .frame(maxWidth: 700)
                         .glassEffect(.regular, in: RoundedRectangle(cornerRadius: Theme.Radius.card))
                         .accessibilityLabel(
                             String(localized: "Profile selection background URL")
                         )
"""

        text = prefix + field + text[cloud_pos:]

    # -----------------------------------------------------------------------
    # 5. Pass the background URL into create/update.
    # -----------------------------------------------------------------------

    if "backgroundUrl:" not in text:
        # We prefer the exact save block markers.
        text = text.replace(
            "avatarUrl: finalAvatarUrl\n",
            "avatarUrl: finalAvatarUrl,\n"
            "                backgroundUrl: finalBackgroundUrl\n",
            2,
        )

    elif "backgroundUrl: finalBackgroundUrl" not in text:
        text = text.replace(
            "avatarUrl: finalAvatarUrl,\n",
            "avatarUrl: finalAvatarUrl,\n"
            "                backgroundUrl: finalBackgroundUrl,\n",
        )

    # -----------------------------------------------------------------------
    # 6. Sanitize the entered URL inside save().
    # -----------------------------------------------------------------------

    if "let finalBackgroundUrl" not in text:
        # Place this immediately before the existing profile/new-profile
        # branch.
        save_marker = (
            "        if let profile = target.profile {"
        )

        if save_marker not in text:
            fail("could not find ProfileEditView save() profile branch")

        sanitizer = """        let trimmedBackgroundUrl =
            backgroundUrl.trimmingCharacters(in: .whitespacesAndNewlines)

        let finalBackgroundUrl: String? = {
            guard !trimmedBackgroundUrl.isEmpty else { return nil }
            guard trimmedBackgroundUrl.count <= 2048 else { return nil }
            guard !trimmedBackgroundUrl.contains(where: { $0.isWhitespace }) else {
                return nil
            }
            guard let url = URL(string: trimmedBackgroundUrl),
                  let scheme = url.scheme?.lowercased(),
                  scheme == "http" || scheme == "https" else {
                return nil
            }
            return String(trimmedBackgroundUrl.prefix(2048))
        }()

"""

        text = text.replace(
            save_marker,
            sanitizer + save_marker,
            1,
        )

    write_if_changed(path, original, text, "profile view")


# ---------------------------------------------------------------------------
# Full-screen remote GIF/static image renderer
# ---------------------------------------------------------------------------

def add_remote_image_file():
    path = SRC / (
        "iosApp/NuvioTV/Screens/"
        "ProfileSelectionRemoteAnimatedImage.swift"
    )

    if path.exists():
        print("remote image view: already exists")
        return

    code = r'''import SwiftUI
import UIKit
import ImageIO

/// Full-screen image used specifically by the profile-selection screen.
///
/// A normal PNG/JPG is shown as a static image.
/// A multi-frame image such as a GIF is decoded into an animated UIImage.
struct ProfileSelectionRemoteAnimatedImage: View {
    let urlString: String

    @State private var image: UIImage?

    var body: some View {
        Group {
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                Color.clear
            }
        }
        .frame(
            maxWidth: .infinity,
            maxHeight: .infinity
        )
        .clipped()
        .overlay(
            Color.black.opacity(0.34)
        )
        .allowsHitTesting(false)
        .task(id: urlString) {
            image = await loadRemoteImage(urlString)
        }
    }

    private func loadRemoteImage(_ value: String) async -> UIImage? {
        let raw = value.trimmingCharacters(
            in: .whitespacesAndNewlines
        )

        guard raw.count <= 2048,
              !raw.contains(where: { $0.isWhitespace }),
              let url = URL(string: raw),
              let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https" else {
            return nil
        }

        do {
            let (data, response) = try await URLSession.shared.data(
                from: url
            )

            if let http = response as? HTTPURLResponse,
               !(200..<300).contains(http.statusCode) {
                return nil
            }

            guard let source = CGImageSourceCreateWithData(
                data as CFData,
                nil
            ) else {
                return nil
            }

            let frameCount = CGImageSourceGetCount(source)

            guard frameCount > 0 else {
                return nil
            }

            // Normal single-frame image.
            if frameCount == 1,
               let cgImage = CGImageSourceCreateImageAtIndex(
                   source,
                   0,
                   nil
               ) {
                return UIImage(cgImage: cgImage)
            }

            // Animated image.
            var frames: [UIImage] = []
            var duration: Double = 0

            for index in 0..<frameCount {
                guard let cgImage = CGImageSourceCreateImageAtIndex(
                    source,
                    index,
                    nil
                ) else {
                    continue
                }

                frames.append(
                    UIImage(cgImage: cgImage)
                )

                if let properties =
                    CGImageSourceCopyPropertiesAtIndex(
                        source,
                        index,
                        nil
                    ) as? [CFString: Any],

                   let gifProperties =
                    properties[kCGImagePropertyGIFDictionary]
                    as? [CFString: Any] {

                    let unclamped =
                        gifProperties[
                            kCGImagePropertyGIFUnclampedDelayTime
                        ] as? Double

                    let clamped =
                        gifProperties[
                            kCGImagePropertyGIFDelayTime
                        ] as? Double

                    let frameDelay =
                        unclamped ?? clamped ?? 0.1

                    duration += max(
                        frameDelay,
                        0.02
                    )
                } else {
                    duration += 0.1
                }
            }

            guard !frames.isEmpty else {
                return nil
            }

            return UIImage.animatedImage(
                with: frames,
                duration: max(duration, 0.1)
            )
        } catch {
            return nil
        }
    }
}
'''

    path.write_text(code, encoding="utf-8")
    print("remote image view: added")


# ---------------------------------------------------------------------------
# Preserve SenPlayer modification
# ---------------------------------------------------------------------------

def patch_plist():
    path = SRC / "iosApp/NuvioTV/Info.plist"

    if not path.exists():
        fail(f"missing {path}")

    text = path.read_text(encoding="utf-8")
    original = text

    if "<string>senplayer</string>" in text:
        print("plist: senplayer already present")
        return

    if "<string>outplayer</string>" in text:
        text = text.replace(
            "<string>outplayer</string>",
            "<string>senplayer</string>",
            1,
        )
    else:
        fail(
            "could not find outplayer entry to preserve "
            "the SenPlayer modification"
        )

    path.write_text(text, encoding="utf-8")
    print("plist: outplayer -> senplayer")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not SRC.exists():
        fail("NuvioMobile source missing")

    print("=== Nuvio SenPlayer Profile GIF Patch ===")

    patch_models()
    patch_repository()
    patch_viewmodel()
    patch_swift_view()
    add_remote_image_file()
    patch_plist()

    print()
    print("PROFILE_GIF_SENPLAYER_PATCH_OK")


if __name__ == "__main__":
    main()
