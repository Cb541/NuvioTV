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


# ============================================================================
# Shared Kotlin profile model
# ============================================================================

def patch_models():
    path = SRC / (
        "shared/src/commonMain/kotlin/"
        "com/nuvio/app/features/profiles/ProfileModels.kt"
    )

    if not path.exists():
        fail(f"missing {path}")

    text = path.read_text(encoding="utf-8")
    original = text

    # ------------------------------------------------------------------------
    # NuvioProfile.backgroundUrl
    # ------------------------------------------------------------------------

    if "val backgroundUrl: String?" not in text:
        pattern = re.compile(
            r'(?P<indent>\s*)@SerialName\("avatar_url"\)\s+'
            r'val avatarUrl:\s*String\?\s*=\s*null,',
            re.MULTILINE,
        )

        match = pattern.search(text)

        if not match:
            fail(
                "could not find avatar_url field in ProfileModels.kt"
            )

        indent = match.group("indent")

        replacement = (
            match.group(0)
            + "\n"
            + indent
            + '@SerialName("background_url") '
              "val backgroundUrl: String? = null,"
        )

        text = (
            text[:match.start()]
            + replacement
            + text[match.end():]
        )

    # ------------------------------------------------------------------------
    # ProfilePushPayload.backgroundUrl
    # ------------------------------------------------------------------------

    background_count = text.count(
        "val backgroundUrl: String? = null"
    )

    if background_count < 2:
        matches = list(
            re.finditer(
                r'(?P<indent>\s*)@SerialName\("avatar_url"\)\s+'
                r'val avatarUrl:\s*String\?\s*=\s*null,',
                text,
                re.MULTILINE,
            )
        )

        if len(matches) < 2:
            fail(
                "could not find the second avatar_url field for "
                "ProfilePushPayload"
            )

        match = matches[1]
        indent = match.group("indent")

        replacement = (
            match.group(0)
            + "\n"
            + indent
            + '@SerialName("background_url") '
              "val backgroundUrl: String? = null,"
        )

        text = (
            text[:match.start()]
            + replacement
            + text[match.end():]
        )

    # ------------------------------------------------------------------------
    # Shared URL validation/helpers
    # ------------------------------------------------------------------------

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

        text = text.rstrip() + helper + "\n"

    write_if_changed(
        path,
        original,
        text,
        "models",
    )


# ============================================================================
# Shared Kotlin repository
# ============================================================================

def patch_repository():
    path = SRC / (
        "shared/src/commonMain/kotlin/"
        "com/nuvio/app/features/profiles/ProfileRepository.kt"
    )

    if not path.exists():
        fail(f"missing {path}")

    text = path.read_text(encoding="utf-8")
    original = text

    # ------------------------------------------------------------------------
    # Add backgroundUrl to createProfile/updateProfile.
    #
    # We locate each function independently so a parameter in one function
    # doesn't accidentally affect another.
    # ------------------------------------------------------------------------

    for function_name in ("createProfile", "updateProfile"):
        function_pattern = re.compile(
            rf"(suspend\s+fun\s+{re.escape(function_name)}\s*\()"
            rf"(?P<body>.*?)"
            rf"(\)\s*\{{)",
            re.S,
        )

        match = function_pattern.search(text)

        if not match:
            print(
                f"WARN: could not locate repository function "
                f"{function_name}"
            )
            continue

        body = match.group("body")

        if "backgroundUrl:" not in body:
            avatar_match = re.search(
                r"(\bavatarUrl\s*:\s*String\?\s*=\s*null,)",
                body,
            )

            if avatar_match:
                new_body = (
                    body[:avatar_match.end()]
                    + "\n        backgroundUrl: String? = null,"
                    + body[avatar_match.end():]
                )

                text = (
                    text[:match.start("body")]
                    + new_body
                    + text[match.end("body"):]
                )

    # ------------------------------------------------------------------------
    # ProfilePushPayload construction.
    # ------------------------------------------------------------------------

    payload_pattern = re.compile(
        r"ProfilePushPayload\s*\((?P<body>.*?)\)",
        re.S,
    )

    def patch_payload(match):
        block = match.group(0)

        if "backgroundUrl =" in block:
            return block

        # profile.backgroundUrl
        profile_avatar = re.search(
            r"(?P<indent>\s*)avatarUrl\s*=\s*profile\.avatarUrl,",
            block,
        )

        if profile_avatar:
            indent = profile_avatar.group("indent")

            return block.replace(
                profile_avatar.group(0),
                profile_avatar.group(0)
                + "\n"
                + indent
                + "backgroundUrl = profile.backgroundUrl,",
                1,
            )

        # function parameter backgroundUrl
        avatar_parameter = re.search(
            r"(?P<indent>\s*)avatarUrl\s*=\s*avatarUrl,",
            block,
        )

        if avatar_parameter:
            indent = avatar_parameter.group("indent")

            return block.replace(
                avatar_parameter.group(0),
                avatar_parameter.group(0)
                + "\n"
                + indent
                + "backgroundUrl = backgroundUrl,",
                1,
            )

        return block

    text = payload_pattern.sub(
        patch_payload,
        text,
    )

    # ------------------------------------------------------------------------
    # Local NuvioProfile mappings.
    # ------------------------------------------------------------------------

    if "backgroundUrl = p.backgroundUrl" not in text:
        profile_mapping = re.compile(
            r"(?P<prefix>NuvioProfile\s*\(.*?"
            r"avatarUrl\s*=\s*p\.avatarUrl,)",
            re.S,
        )

        match = profile_mapping.search(text)

        if match:
            replacement = (
                match.group("prefix")
                + "\n                "
                  "backgroundUrl = p.backgroundUrl,"
            )

            text = (
                text[:match.start()]
                + replacement
                + text[match.end():]
            )

    # ------------------------------------------------------------------------
    # Make sure the repository now references backgroundUrl.
    # ------------------------------------------------------------------------

    if "backgroundUrl" not in text:
        fail(
            "repository patch made no backgroundUrl changes"
        )

    write_if_changed(
        path,
        original,
        text,
        "repository",
    )


# ============================================================================
# tvOS ProfilesViewModel.swift
# ============================================================================

def patch_viewmodel():
    path = find_file(
        "ProfilesViewModel.swift",
        "class ProfilesViewModel",
    )

    text = path.read_text(encoding="utf-8")
    original = text

    # ------------------------------------------------------------------------
    # createProfile
    # ------------------------------------------------------------------------

    create_pattern = re.compile(
        r"(func\s+createProfile\s*\("
        r".*?"
        r"\bavatarUrl\s*:\s*String\?,)",
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

    # ------------------------------------------------------------------------
    # updateProfile
    # ------------------------------------------------------------------------

    update_pattern = re.compile(
        r"(func\s+updateProfile\s*\("
        r".*?"
        r"\bavatarUrl\s*:\s*String\?,)",
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

    # ------------------------------------------------------------------------
    # Forward backgroundUrl to repository calls.
    # ------------------------------------------------------------------------

    if "backgroundUrl: backgroundUrl" not in text:
        text = text.replace(
            "avatarUrl: avatarUrl,\n",
            "avatarUrl: avatarUrl,\n"
            "            backgroundUrl: backgroundUrl,\n",
        )

    write_if_changed(
        path,
        original,
        text,
        "viewmodel",
    )


# ============================================================================
# tvOS ProfileSelectionView.swift
# ============================================================================

def patch_swift_view():
    path = SRC / "iosApp/NuvioTV/Screens/ProfileSelectionView.swift"

    if not path.exists():
        fail(f"missing {path}")

    text = path.read_text(encoding="utf-8")
    original = text

    # ------------------------------------------------------------------------
    # 1. Profile-selection background
    # ------------------------------------------------------------------------

    if "ProfileSelectionRemoteAnimatedImage" not in text:

        # Find the first ZStack containing the existing theme background.
        background_marker = (
            "Theme.Palette.background.ignoresSafeArea()"
        )

        background_pos = text.find(background_marker)

        if background_pos < 0:
            fail(
                "could not find profile-selection theme background"
            )

        # Locate the beginning of the ZStack containing that background.
        zstack_pos = text.rfind(
            "ZStack {",
            0,
            background_pos,
        )

        if zstack_pos < 0:
            fail(
                "could not find ProfileSelectionView ZStack"
            )

        # Determine indentation from the existing ZStack.
        line_start = text.rfind("\n", 0, zstack_pos) + 1
        zstack_indent = text[line_start:zstack_pos]

        child_indent = zstack_indent + "    "

        background_code = (
            f"{child_indent}if let backgroundURL = "
            "profileSelectionBackgroundURL {\n"
            f"{child_indent}    "
            "ProfileSelectionRemoteAnimatedImage("
            "urlString: backgroundURL\n"
            f"{child_indent}    )\n"
            f"{child_indent}    .ignoresSafeArea()\n"
            f"{child_indent}\n"
        )

        text = (
            text[:background_pos]
            + background_code
            + text[background_pos:]
        )

    # ------------------------------------------------------------------------
    # 2. Background URL computed property
    # ------------------------------------------------------------------------

    if "profileSelectionBackgroundURL" not in text:

        body_marker = "    var body: some View {"

        body_pos = text.find(body_marker)

        if body_pos < 0:
            fail(
                "could not find ProfileSelectionView body"
            )

        property_code = """    private var profileSelectionBackgroundURL: String? {
        let profile = model.activeProfile ?? model.profiles.first

        return profile.flatMap { profile in
            ProfileModelsKt.profileBackgroundImageUrl(
                profile: profile
            )
        }
    }

"""

        text = (
            text[:body_pos]
            + property_code
            + text[body_pos:]
        )

    # ------------------------------------------------------------------------
    # 3. Background URL editing state
    # ------------------------------------------------------------------------

    if "@State private var backgroundUrl: String" not in text:

        marker = "@State private var avatarId: String?"

        pos = text.find(marker)

        if pos < 0:
            fail(
                "could not find avatarId state declaration"
            )

        line_end = text.find("\n", pos)

        text = (
            text[:line_end + 1]
            + "    @State private var backgroundUrl: String\n"
            + text[line_end + 1:]
        )

    # ------------------------------------------------------------------------
    # 4. Initialize background URL
    # ------------------------------------------------------------------------

    if "_backgroundUrl = State" not in text:

        marker = "_avatarId = State(initialValue: target.profile?.avatarId)"

        pos = text.find(marker)

        if pos < 0:
            fail(
                "could not find avatarId initializer"
            )

        line_end = text.find("\n", pos)

        text = (
            text[:line_end + 1]
            + (
                '        _backgroundUrl = State('
                'initialValue: target.profile?.backgroundUrl ?? "")\n'
            )
            + text[line_end + 1:]
        )

    # ------------------------------------------------------------------------
    # 5. Add Custom background URL TextField.
    #
    # Instead of depending on indentation, find the Name TextField and then
    # insert immediately before the "Cloud avatar catalog" section.
    # ------------------------------------------------------------------------

    if 'TextField("Custom background URL"' not in text:

        name_pos = text.find(
            'TextField("Name", text: $name)'
        )

        if name_pos < 0:
            fail(
                'could not find TextField("Name", text: $name)'
            )

        cloud_pos = text.find(
            "// Cloud avatar catalog",
            name_pos,
        )

        if cloud_pos < 0:
            fail(
                "could not find Cloud avatar catalog marker "
                "after Name field"
            )

        # Determine indentation of the cloud catalog line.
        cloud_line_start = text.rfind(
            "\n",
            0,
            cloud_pos,
        ) + 1

        indentation = text[
            cloud_line_start:cloud_pos
        ]

        field = (
            indentation
            + 'TextField("Custom background URL", '
              'text: $backgroundUrl)\n'
            + indentation
            + "    .textFieldStyle(.plain)\n"
            + indentation
            + "    .font(Theme.Font.body)\n"
            + indentation
            + "    .foregroundStyle(Theme.Palette.textPrimary)\n"
            + indentation
            + "    .padding(Theme.Spacing.lg)\n"
            + indentation
            + "    .frame(maxWidth: 700)\n"
            + indentation
            + "    .glassEffect(\n"
            + indentation
            + "        .regular,\n"
            + indentation
            + "        in: RoundedRectangle("
              "cornerRadius: Theme.Radius.card)\n"
            + indentation
            + "    )\n"
            + indentation
            + "    .accessibilityLabel(\n"
            + indentation
            + '        String(localized: '
              '"Profile selection background URL")\n'
            + indentation
            + "    )\n"
        )

        text = (
            text[:cloud_pos]
            + field
            + text[cloud_pos:]
        )

    # ------------------------------------------------------------------------
    # 6. Sanitize/save background URL.
    # ------------------------------------------------------------------------

    if "let finalBackgroundUrl" not in text:

        save_marker = "if let profile = target.profile {"

        save_pos = text.find(save_marker)

        if save_pos < 0:
            fail(
                "could not find profile save branch"
            )

        line_start = text.rfind(
            "\n",
            0,
            save_pos,
        ) + 1

        indent = text[line_start:save_pos]

        sanitizer = (
            f"{indent}let trimmedBackgroundUrl = "
              "backgroundUrl.trimmingCharacters("
              ".whitespacesAndNewlines)\n\n"
            f"{indent}let finalBackgroundUrl: String? = {{\n"
            f"{indent}    guard !trimmedBackgroundUrl.isEmpty "
              "else {{ return nil }}\n"
            f"{indent}    guard trimmedBackgroundUrl.count <= 2048 "
              "else {{ return nil }}\n"
            f"{indent}    guard !trimmedBackgroundUrl.contains("
              "where: {{ $0.isWhitespace }}) else {{\n"
            f"{indent}        return nil\n"
            f"{indent}    }}\n"
            f"{indent}    guard let url = "
              "URL(string: trimmedBackgroundUrl),\n"
            f"{indent}          let scheme = "
              "url.scheme?.lowercased(),\n"
            f"{indent}          scheme == \"http\" || "
              "scheme == \"https\" else {{\n"
            f"{indent}        return nil\n"
            f"{indent}    }}\n"
            f"{indent}    return trimmedBackgroundUrl\n"
            f"{indent}}}()\n\n"
        )

        text = (
            text[:line_start]
            + sanitizer
            + text[line_start:]
        )

    # ------------------------------------------------------------------------
    # 7. Forward finalBackgroundUrl into create/update calls.
    # ------------------------------------------------------------------------

    if "backgroundUrl: finalBackgroundUrl" not in text:

        # Handles both forms:
        #
        #     avatarUrl: finalAvatarUrl
        #
        # and:
        #
        #     avatarUrl: finalAvatarUrl,
        #

        plain_pattern = "avatarUrl: finalAvatarUrl\n"

        if plain_pattern in text:
            text = text.replace(
                plain_pattern,
                "avatarUrl: finalAvatarUrl,\n"
                "                backgroundUrl: finalBackgroundUrl\n",
                2,
            )
        else:
            comma_pattern = "avatarUrl: finalAvatarUrl,\n"

            occurrences = text.count(comma_pattern)

            if occurrences:
                text = text.replace(
                    comma_pattern,
                    "avatarUrl: finalAvatarUrl,\n"
                    "                backgroundUrl: finalBackgroundUrl,\n",
                    2,
                )

    write_if_changed(
        path,
        original,
        text,
        "profile view",
    )


# ============================================================================
# Animated remote image view
# ============================================================================

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

/// Remote full-screen image used by the profile-selection screen.
///
/// Static images are displayed normally.
/// Multi-frame images such as GIF files are decoded into an animated UIImage.
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

    private func loadRemoteImage(
        _ value: String
    ) async -> UIImage? {

        let raw = value.trimmingCharacters(
            in: .whitespacesAndNewlines
        )

        guard raw.count <= 2048 else {
            return nil
        }

        guard !raw.contains(where: { $0.isWhitespace }) else {
            return nil
        }

        guard let url = URL(string: raw) else {
            return nil
        }

        guard let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https" else {
            return nil
        }

        do {
            let (data, response) =
                try await URLSession.shared.data(
                    from: url
                )

            if let httpResponse =
                response as? HTTPURLResponse {

                guard (200..<300).contains(
                    httpResponse.statusCode
                ) else {
                    return nil
                }
            }

            guard let source =
                CGImageSourceCreateWithData(
                    data as CFData,
                    nil
                ) else {
                return nil
            }

            let frameCount =
                CGImageSourceGetCount(source)

            guard frameCount > 0 else {
                return nil
            }

            // Single-frame JPG/PNG/WebP/etc.
            if frameCount == 1,
               let cgImage =
                CGImageSourceCreateImageAtIndex(
                    source,
                    0,
                    nil
                ) {

                return UIImage(cgImage: cgImage)
            }

            // Animated image / GIF.
            var frames: [UIImage] = []
            var duration: Double = 0

            for index in 0..<frameCount {

                guard let cgImage =
                    CGImageSourceCreateImageAtIndex(
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
                    properties[
                        kCGImagePropertyGIFDictionary
                    ] as? [CFString: Any] {

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
                duration: max(
                    duration,
                    0.1
                )
            )

        } catch {
            return nil
        }
    }
}
'''

    path.write_text(
        code,
        encoding="utf-8",
    )

    print("remote image view: added")


# ============================================================================
# Preserve SenPlayer support
# ============================================================================

def patch_plist():
    path = SRC / "iosApp/NuvioTV/Info.plist"

    if not path.exists():
        fail(f"missing {path}")

    text = path.read_text(
        encoding="utf-8"
    )

    if "<string>senplayer</string>" in text:
        print("plist: senplayer already present")
        return

    if "<string>outplayer</string>" in text:
        text = text.replace(
            "<string>outplayer</string>",
            "<string>senplayer</string>",
            1,
        )

        path.write_text(
            text,
            encoding="utf-8",
        )

        print("plist: outplayer -> senplayer")
        return

    fail(
        "could not find outplayer entry to preserve "
        "SenPlayer support"
    )


# ============================================================================
# Main
# ============================================================================

def main():

    if not SRC.exists():
        fail("NuvioMobile source missing")

    print()
    print("==============================================")
    print(" Nuvio SenPlayer Profile GIF Background Patch")
    print("==============================================")
    print()

    patch_models()
    patch_repository()
    patch_viewmodel()
    patch_swift_view()
    add_remote_image_file()
    patch_plist()

    print()
    print("==============================================")
    print(" PROFILE_GIF_SENPLAYER_PATCH_OK")
    print("==============================================")
    print()


if __name__ == "__main__":
    main()
