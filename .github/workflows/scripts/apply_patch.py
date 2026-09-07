#!/usr/bin/env python3

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "NuvioMobile"


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def write_file(path, original, updated, label):
    if updated == original:
        print(f"{label}: already patched")
        return

    path.write_text(updated, encoding="utf-8")
    print(f"{label}: patched")


# ============================================================================
# PROFILE MODELS
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

    # Add background_url to both profile-related data classes.
    if "val backgroundUrl: String? = null" not in text:

        pattern = re.compile(
            r'(?m)^(\s*)@SerialName\("avatar_url"\)\s+'
            r'val avatarUrl:\s*String\?\s*=\s*null,'
        )

        matches = list(pattern.finditer(text))

        if len(matches) < 2:
            fail(
                "expected avatar_url fields for NuvioProfile "
                "and ProfilePushPayload"
            )

        # Work backwards so indexes remain valid.
        for match in reversed(matches[:2]):
            indent = match.group(1)

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

    # Shared helper exposed to Swift.
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

    write_file(path, original, text, "models")


# ============================================================================
# PROFILE REPOSITORY
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

    # Add backgroundUrl to createProfile/updateProfile.
    for function_name in ("createProfile", "updateProfile"):

        pattern = re.compile(
            rf"(?s)"
            rf"(suspend\s+fun\s+{re.escape(function_name)}\s*\()"
            rf"(.*?)"
            rf"(\)\s*\{{)"
        )

        match = pattern.search(text)

        if not match:
            fail(
                f"could not find repository function {function_name}"
            )

        body = match.group(2)

        if "backgroundUrl:" not in body:

            avatar_match = re.search(
                r"(\bavatarUrl\s*:\s*String\?\s*=\s*null,)",
                body,
            )

            if not avatar_match:
                fail(
                    f"could not find avatarUrl parameter "
                    f"in {function_name}"
                )

            new_body = (
                body[:avatar_match.end()]
                + "\n        backgroundUrl: String? = null,"
                + body[avatar_match.end():]
            )

            text = (
                text[:match.start(2)]
                + new_body
                + text[match.end(2):]
            )

    # Existing profile -> push payload.
    if "backgroundUrl = profile.backgroundUrl" not in text:
        text = text.replace(
            "avatarUrl = profile.avatarUrl,",
            "avatarUrl = profile.avatarUrl,\n"
            "                backgroundUrl = profile.backgroundUrl,",
        )

    # New profile -> push payload.
    if "backgroundUrl = backgroundUrl" not in text:
        text = text.replace(
            "avatarUrl = avatarUrl,",
            "avatarUrl = avatarUrl,\n"
            "            backgroundUrl = backgroundUrl,",
        )

    # Local profile reconstruction.
    if "backgroundUrl = p.backgroundUrl" not in text:
        text = text.replace(
            "avatarUrl = p.avatarUrl,",
            "avatarUrl = p.avatarUrl,\n"
            "                backgroundUrl = p.backgroundUrl,",
        )

    if "backgroundUrl" not in text:
        fail(
            "repository patch made no backgroundUrl changes"
        )

    write_file(path, original, text, "repository")


# ============================================================================
# tvOS PROFILES VIEW MODEL
# ============================================================================

def patch_viewmodel():
    path = SRC / "iosApp/NuvioTV/Screens/ProfilesViewModel.swift"

    if not path.exists():
        fail(f"missing {path}")

    text = path.read_text(encoding="utf-8")
    original = text

    # createProfile
    pattern = re.compile(
        r"(?s)"
        r"(func\s+createProfile\s*\()"
        r"(.*?)"
        r"(\n\s*\)\s*\{)"
    )

    match = pattern.search(text)

    if not match:
        fail(
            "could not find createProfile "
            "in ProfilesViewModel.swift"
        )

    body = match.group(2)

    if "backgroundUrl:" not in body:

        avatar_match = re.search(
            r"(?m)^(\s*)avatarUrl:\s*String\?\s*=\s*nil,",
            body,
        )

        if not avatar_match:
            fail(
                "could not find createProfile avatarUrl parameter"
            )

        indent = avatar_match.group(1)

        new_body = (
            body[:avatar_match.end()]
            + "\n"
            + indent
            + "backgroundUrl: String? = nil,"
            + body[avatar_match.end():]
        )

        text = (
            text[:match.start(2)]
            + new_body
            + text[match.end(2):]
        )

    # updateProfile
    pattern = re.compile(
        r"(?s)"
        r"(func\s+updateProfile\s*\()"
        r"(.*?)"
        r"(\n\s*\)\s*\{)"
    )

    match = pattern.search(text)

    if not match:
        fail(
            "could not find updateProfile "
            "in ProfilesViewModel.swift"
        )

    body = match.group(2)

    if "backgroundUrl:" not in body:

        avatar_match = re.search(
            r"(?m)^(\s*)avatarUrl:\s*String\?\s*=\s*nil,",
            body,
        )

        if not avatar_match:
            fail(
                "could not find updateProfile avatarUrl parameter"
            )

        indent = avatar_match.group(1)

        new_body = (
            body[:avatar_match.end()]
            + "\n"
            + indent
            + "backgroundUrl: String? = nil,"
            + body[avatar_match.end():]
        )

        text = (
            text[:match.start(2)]
            + new_body
            + text[match.end(2):]
        )

    # Forward to repository.
    if "backgroundUrl: backgroundUrl" not in text:
        text = text.replace(
            "avatarUrl: avatarUrl,",
            "avatarUrl: avatarUrl,\n"
            "            backgroundUrl: backgroundUrl,",
        )

    write_file(path, original, text, "viewmodel")


# ============================================================================
# PROFILE SELECTION VIEW
# ============================================================================

def patch_selection_view():
    path = SRC / "iosApp/NuvioTV/Screens/ProfileSelectionView.swift"

    if not path.exists():
        fail(f"missing {path}")

    text = path.read_text(encoding="utf-8")
    original = text

    # ========================================================================
    # ProfileSelectionView
    # ========================================================================

    selection_start = text.find(
        "struct ProfileSelectionView: View"
    )

    if selection_start < 0:
        fail("could not find ProfileSelectionView")

    selection_end = text.find(
        "/// Focus-aware profile tile label",
        selection_start,
    )

    if selection_end < 0:
        fail(
            "could not determine end of ProfileSelectionView"
        )

    selection = text[
        selection_start:selection_end
    ]

    # Add background property.
    if "profileSelectionBackgroundURL" not in selection:

        body_marker = "    var body: some View {"

        body_pos = selection.find(body_marker)

        if body_pos < 0:
            fail(
                "could not find ProfileSelectionView body"
            )

        property_block = """    private var profileSelectionBackgroundURL: String? {
        model.activeProfile?.backgroundUrl
            ?? model.profiles.first?.backgroundUrl
    }

"""

        selection = (
            selection[:body_pos]
            + property_block
            + selection[body_pos:]
        )

    # Add animated background.
    if "ProfileSelectionRemoteAnimatedImage" not in selection:

        marker = (
            "Theme.Palette.background.ignoresSafeArea()"
        )

        marker_pos = selection.find(marker)

        if marker_pos < 0:
            fail(
                "could not find ProfileSelectionView "
                "theme background"
            )

        line_start = selection.rfind(
            "\n",
            0,
            marker_pos,
        ) + 1

        indentation = selection[
            line_start:marker_pos
        ]

        background = (
            indentation
            + "if let backgroundURL = "
              "profileSelectionBackgroundURL {\n"
            + indentation
            + "    ProfileSelectionRemoteAnimatedImage("
              "urlString: backgroundURL)\n"
            + indentation
            + "        .ignoresSafeArea()\n"
            + indentation
            + "}\n"
            + indentation
        )

        selection = (
            selection[:marker_pos]
            + background
            + selection[marker_pos:]
        )

    text = (
        text[:selection_start]
        + selection
        + text[selection_end:]
    )

    # ========================================================================
    # ProfileEditView
    # ========================================================================

    edit_start = text.find(
        "struct ProfileEditView: View"
    )

    if edit_start < 0:
        fail("could not find ProfileEditView")

    edit_end = text.find(
        "/// Focus visuals for the circular avatar",
        edit_start,
    )

    if edit_end < 0:
        fail(
            "could not determine end of ProfileEditView"
        )

    edit = text[
        edit_start:edit_end
    ]

    # ------------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------------

    if "@State private var backgroundUrl: String" not in edit:

        marker = "    @State private var avatarId: String?"

        pos = edit.find(marker)

        if pos < 0:
            fail(
                "could not find ProfileEditView avatarId state"
            )

        line_end = edit.find("\n", pos)

        edit = (
            edit[:line_end + 1]
            + "    @State private var backgroundUrl: String\n"
            + edit[line_end + 1:]
        )

    # ------------------------------------------------------------------------
    # Initial value
    # ------------------------------------------------------------------------

    if "_backgroundUrl = State" not in edit:

        marker = (
            "_avatarId = State("
            "initialValue: target.profile?.avatarId)"
        )

        pos = edit.find(marker)

        if pos < 0:
            fail(
                "could not find ProfileEditView avatarId initializer"
            )

        line_end = edit.find("\n", pos)

        initializer = (
            "        _backgroundUrl = State("
            'initialValue: target.profile?.backgroundUrl ?? "")\n'
        )

        edit = (
            edit[:line_end + 1]
            + initializer
            + edit[line_end + 1:]
        )

    # ------------------------------------------------------------------------
    # Text field
    # ------------------------------------------------------------------------

    if 'TextField("Custom background URL"' not in edit:

        name_pos = edit.find(
            'TextField("Name", text: $name)'
        )

        if name_pos < 0:
            fail(
                'could not find TextField("Name", text: $name)'
            )

        cloud_pos = edit.find(
            "// Cloud avatar catalog",
            name_pos,
        )

        if cloud_pos < 0:
            fail(
                "could not find Cloud avatar catalog "
                "after Name field"
            )

        line_start = edit.rfind(
            "\n",
            0,
            cloud_pos,
        ) + 1

        indentation = edit[
            line_start:cloud_pos
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

        edit = (
            edit[:cloud_pos]
            + field
            + edit[cloud_pos:]
        )

    # ------------------------------------------------------------------------
    # Sanitize background URL
    # ------------------------------------------------------------------------

    if "let finalBackgroundUrl" not in edit:

        marker = "if let profile = target.profile {"

        pos = edit.find(marker)

        if pos < 0:
            fail(
                "could not find ProfileEditView save branch"
            )

        line_start = edit.rfind(
            "\n",
            0,
            pos,
        ) + 1

        indentation = edit[
            line_start:pos
        ]

        sanitizer = (
            indentation
            + "let trimmedBackgroundUrl = "
              "backgroundUrl.trimmingCharacters("
              ".whitespacesAndNewlines)\n\n"
            + indentation
            + "let finalBackgroundUrl: String? = {\n"
            + indentation
            + "    guard !trimmedBackgroundUrl.isEmpty "
              "else { return nil }\n"
            + indentation
            + "    guard trimmedBackgroundUrl.count <= 2048 "
              "else { return nil }\n"
            + indentation
            + "    guard !trimmedBackgroundUrl.contains("
              "where: { $0.isWhitespace }) else {\n"
            + indentation
            + "        return nil\n"
            + indentation
            + "    }\n"
            + indentation
            + "    guard let url = "
              "URL(string: trimmedBackgroundUrl),\n"
            + indentation
            + "          let scheme = "
              "url.scheme?.lowercased(),\n"
            + indentation
            + '          scheme == "http" || '
              'scheme == "https" else {\n'
            + indentation
            + "        return nil\n"
            + indentation
            + "    }\n"
            + indentation
            + "    return trimmedBackgroundUrl\n"
            + indentation
            + "}()\n\n"
        )

        edit = (
            edit[:line_start]
            + sanitizer
            + edit[line_start:]
        )

    # ------------------------------------------------------------------------
    # Forward backgroundUrl into create/update calls.
    # ------------------------------------------------------------------------

    if "backgroundUrl: finalBackgroundUrl" not in edit:

        plain = (
            "avatarUrl: finalAvatarUrl\n"
        )

        if plain in edit:
            edit = edit.replace(
                plain,
                "avatarUrl: finalAvatarUrl,\n"
                "                "
                "backgroundUrl: finalBackgroundUrl\n",
                2,
            )
        else:
            comma = (
                "avatarUrl: finalAvatarUrl,\n"
            )

            edit = edit.replace(
                comma,
                "avatarUrl: finalAvatarUrl,\n"
                "                "
                "backgroundUrl: finalBackgroundUrl,\n",
                2,
            )

    text = (
        text[:edit_start]
        + edit
        + text[edit_end:]
    )

    write_file(
        path,
        original,
        text,
        "profile selection view",
    )


# ============================================================================
# REMOTE GIF BACKGROUND VIEW
# ============================================================================

def add_remote_image_file():
    path = SRC / (
        "iosApp/NuvioTV/Screens/"
        "ProfileSelectionRemoteAnimatedImage.swift"
    )

    if path.exists():
        print("remote GIF view: already present")
        return

    code = r'''import SwiftUI
import UIKit
import ImageIO

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

        guard !raw.contains(
            where: { $0.isWhitespace }
        ) else {
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

            // Static image.
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

    print("remote GIF view: added")


# ============================================================================
# SENPLAYER PLIST
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

    if "<string>outplayer</string>" not in text:
        fail(
            "could not find outplayer entry needed "
            "for SenPlayer support"
        )

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


# ============================================================================
# MAIN
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
    patch_selection_view()
    add_remote_image_file()
    patch_plist()

    print()
    print("==============================================")
    print(" PROFILE_GIF_SENPLAYER_PATCH_OK")
    print("==============================================")
    print()


if __name__ == "__main__":
    main()
