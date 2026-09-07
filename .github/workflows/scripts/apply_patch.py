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

    # Add background_url to NuvioProfile.
    if "val backgroundUrl: String? = null" not in text:
        pattern = re.compile(
            r'(?m)^(\s*)@SerialName\("avatar_url"\)\s+'
            r'val avatarUrl:\s*String\?\s*=\s*null,'
        )

        matches = list(pattern.finditer(text))

        if len(matches) < 2:
            fail(
                "expected NuvioProfile and ProfilePushPayload avatar_url fields"
            )

        # Insert after the first avatar_url field.
        first = matches[0]
        indent = first.group(1)

        replacement = (
            first.group(0)
            + "\n"
            + indent
            + '@SerialName("background_url") '
              "val backgroundUrl: String? = null,"
        )

        text = (
            text[:first.start()]
            + replacement
            + text[first.end():]
        )

        # Find the second avatar_url after the first insertion.
        second_match = re.search(
            r'(?m)^(\s*)@SerialName\("avatar_url"\)\s+'
            r'val avatarUrl:\s*String\?\s*=\s*null,',
            text[first.start() + len(replacement):],
        )

        if not second_match:
            fail("could not find ProfilePushPayload avatar_url field")

        second_start = first.start() + len(replacement) + second_match.start()
        second_end = first.start() + len(replacement) + second_match.end()

        indent2 = second_match.group(1)

        replacement2 = (
            second_match.group(0)
            + "\n"
            + indent2
            + '@SerialName("background_url") '
              "val backgroundUrl: String? = null,"
        )

        text = (
            text[:second_start]
            + replacement2
            + text[second_end:]
        )

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

    # ------------------------------------------------------------------------
    # createProfile / updateProfile parameters
    # ------------------------------------------------------------------------

    for function_name in ("createProfile", "updateProfile"):

        function_match = re.search(
            rf"(?s)(suspend\s+fun\s+{function_name}\s*\()(.*?)(\)\s*\{{)",
            text,
        )

        if not function_match:
            fail(
                f"could not find repository function {function_name}"
            )

        body = function_match.group(2)

        if "backgroundUrl:" not in body:
            avatar_parameter = re.search(
                r"(\bavatarUrl\s*:\s*String\?\s*=\s*null,)",
                body,
            )

            if not avatar_parameter:
                fail(
                    f"could not find avatarUrl parameter in "
                    f"{function_name}"
                )

            new_body = (
                body[:avatar_parameter.end()]
                + "\n        backgroundUrl: String? = null,"
                + body[avatar_parameter.end():]
            )

            text = (
                text[:function_match.start(2)]
                + new_body
                + text[function_match.end(2):]
            )

    # ------------------------------------------------------------------------
    # Existing profile -> payload
    # ------------------------------------------------------------------------

    text = text.replace(
        "avatarUrl = profile.avatarUrl,\n",
        "avatarUrl = profile.avatarUrl,\n"
        "                backgroundUrl = profile.backgroundUrl,\n",
    )

    # ------------------------------------------------------------------------
    # New profile -> payload
    # ------------------------------------------------------------------------

    text = text.replace(
        "avatarUrl = avatarUrl,\n",
        "avatarUrl = avatarUrl,\n"
        "            backgroundUrl = backgroundUrl,\n",
    )

    # ------------------------------------------------------------------------
    # Local NuvioProfile reconstruction
    # ------------------------------------------------------------------------

    text = text.replace(
        "avatarUrl = p.avatarUrl,\n",
        "avatarUrl = p.avatarUrl,\n"
        "                backgroundUrl = p.backgroundUrl,\n",
    )

    # ------------------------------------------------------------------------
    # Make sure every profile field was actually introduced.
    # ------------------------------------------------------------------------

    if "backgroundUrl" not in text:
        fail("repository patch made no backgroundUrl changes")

    write_file(path, original, text, "repository")


# ============================================================================
# tvOS PROFILE VIEW MODEL
# ============================================================================

def patch_viewmodel():
    path = SRC / "iosApp/NuvioTV/Screens/ProfilesViewModel.swift"

    if not path.exists():
        fail(f"missing {path}")

    text = path.read_text(encoding="utf-8")
    original = text

    # ------------------------------------------------------------------------
    # createProfile signature
    # ------------------------------------------------------------------------

    create_match = re.search(
        r"(?s)(func\s+createProfile\s*\()(.*?)(\n\s*\)\s*\{)",
        text,
    )

    if not create_match:
        fail("could not find createProfile in ProfilesViewModel.swift")

    create_body = create_match.group(2)

    if "backgroundUrl:" not in create_body:
        avatar_line = re.search(
            r"(?m)^(\s*)avatarUrl:\s*String\?\s*=\s*nil,",
            create_body,
        )

        if not avatar_line:
            fail("could not find createProfile avatarUrl parameter")

        indent = avatar_line.group(1)

        new_body = (
            create_body[:avatar_line.end()]
            + "\n"
            + indent
            + "backgroundUrl: String? = nil,"
            + create_body[avatar_line.end():]
        )

        text = (
            text[:create_match.start(2)]
            + new_body
            + text[create_match.end(2):]
        )

    # ------------------------------------------------------------------------
    # updateProfile signature
    # ------------------------------------------------------------------------

    update_match = re.search(
        r"(?s)(func\s+updateProfile\s*\()(.*?)(\n\s*\)\s*\{)",
        text,
    )

    if not update_match:
        fail("could not find updateProfile in ProfilesViewModel.swift")

    update_body = update_match.group(2)

    if "backgroundUrl:" not in update_body:
        avatar_line = re.search(
            r"(?m)^(\s*)avatarUrl:\s*String\?\s*=\s*nil,",
            update_body,
        )

        if not avatar_line:
            fail("could not find updateProfile avatarUrl parameter")

        indent = avatar_line.group(1)

        new_body = (
            update_body[:avatar_line.end()]
            + "\n"
            + indent
            + "backgroundUrl: String? = nil,"
            + update_body[avatar_line.end():]
        )

        text = (
            text[:update_match.start(2)]
            + new_body
            + text[update_match.end(2):]
        )

    # ------------------------------------------------------------------------
    # Forward backgroundUrl to repository calls.
    # ------------------------------------------------------------------------

    text = text.replace(
        "avatarUrl: avatarUrl,\n",
        "avatarUrl: avatarUrl,\n"
        "            backgroundUrl: backgroundUrl,\n",
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
    # ProfileSelectionView section
    # ========================================================================

    selection_start = text.find("struct ProfileSelectionView: View")

    if selection_start < 0:
        fail("could not find ProfileSelectionView")

    selection_end = text.find(
        "/// Focus-aware profile tile label",
        selection_start,
    )

    if selection_end < 0:
        fail("could not determine end of ProfileSelectionView")

    selection = text[selection_start:selection_end]

    # ------------------------------------------------------------------------
    # Add background property
    # ------------------------------------------------------------------------

    if "private var profileSelectionBackgroundURL" not in selection:

        body_marker = "    var body: some View {"

        body_pos = selection.find(body_marker)

        if body_pos < 0:
            fail("could not find ProfileSelectionView body")

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

    # ------------------------------------------------------------------------
    # Add remote background inside the selection ZStack.
    # ------------------------------------------------------------------------

    if "ProfileSelectionRemoteAnimatedImage" not in selection:

        background_marker = (
            "            Theme.Palette.background.ignoresSafeArea()"
        )

        background_pos = selection.find(background_marker)

        if background_pos < 0:
            fail(
                "could not find ProfileSelectionView theme background"
            )

        background_code = """            if let backgroundURL = profileSelectionBackgroundURL {
                ProfileSelectionRemoteAnimatedImage(urlString: backgroundURL)
                    .ignoresSafeArea()
            }

"""

        selection = (
            selection[:background_pos]
            + background_code
            + selection[background_pos:]
        )

    # Reassemble main file.
    text = (
        text[:selection_start]
        + selection
        + text[selection_end:]
    )

    # ========================================================================
    # ProfileEditView section
    # ========================================================================

    edit_start = text.find("struct ProfileEditView: View")

    if edit_start < 0:
        fail("could not find ProfileEditView")

    edit_end = text.find(
        "/// Focus visuals for the circular avatar",
        edit_start,
    )

    if edit_end < 0:
        fail("could not determine end of ProfileEditView")

    edit = text[edit_start:edit_end]

    # ------------------------------------------------------------------------
    # Add background URL state
    # ------------------------------------------------------------------------

    if "@State private var backgroundUrl: String" not in edit:

        marker = "    @State private var avatarId: String?\n"

        pos = edit.find(marker)

        if pos < 0:
            fail(
                "could not find ProfileEditView avatarId state"
            )

        edit = (
            edit[:pos]
            + marker
            + "    @State private var backgroundUrl: String\n"
            + edit[pos + len(marker):]
        )

    # ------------------------------------------------------------------------
    # Initialize background URL
    # ------------------------------------------------------------------------

    if "_backgroundUrl = State" not in edit:

        marker = (
            "        _avatarId = State("
            "initialValue: target.profile?.avatarId)\n"
        )

        pos = edit.find(marker)

        if pos < 0:
            fail(
                "could not find ProfileEditView avatarId initializer"
            )

        initializer = (
            marker
            + '        _backgroundUrl = State('
              'initialValue: target.profile?.backgroundUrl ?? "")\n'
        )

        edit = (
            edit[:pos]
            + initializer
            + edit[pos + len(marker):]
        )

    # ------------------------------------------------------------------------
    # Add Custom background URL field
    # ------------------------------------------------------------------------

    if 'TextField("Custom background URL"' not in edit:

        cloud_marker = "// Cloud avatar catalog"

        cloud_pos = edit.find(cloud_marker)

        if cloud_pos < 0:
            fail(
                "could not find Cloud avatar catalog section"
            )

        # Match the existing indentation.
        line_start = edit.rfind("\n", 0, cloud_pos) + 1

        indentation = edit[line_start:cloud_pos]

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
    # Add sanitized background URL before save branches.
    # ------------------------------------------------------------------------

    if "let finalBackgroundUrl" not in edit:

        marker = "        if let profile = target.profile {"

        pos = edit.find(marker)

        if pos < 0:
            fail(
                "could not find ProfileEditView save() branch"
            )

        sanitizer = """        let trimmedBackgroundUrl =
            backgroundUrl.trimmingCharacters(in: .whitespacesAndNewlines)

        let finalBackgroundUrl: String? = {
            guard !trimmedBackgroundUrl.isEmpty else {
                return nil
            }

            guard trimmedBackgroundUrl.count <= 2048 else {
                return nil
            }

            guard !trimmedBackgroundUrl.contains(
                where: { $0.isWhitespace }
            ) else {
                return nil
            }

            guard let url = URL(string: trimmedBackgroundUrl),
                  let scheme = url.scheme?.lowercased(),
                  scheme == "http" || scheme == "https" else {
                return nil
            }

            return trimmedBackgroundUrl
        }()

"""

        edit = (
            edit[:pos]
            + sanitizer
            + edit[pos:]
        )

    # ------------------------------------------------------------------------
    # Add backgroundUrl to updateProfile/createProfile calls.
    # ------------------------------------------------------------------------

    if "backgroundUrl: finalBackgroundUrl" not in edit:

        edit = edit.replace(
            "                avatarUrl: finalAvatarUrl\n",
            "                avatarUrl: finalAvatarUrl,\n"
            "                backgroundUrl: finalBackgroundUrl\n",
        )

        edit = edit.replace(
            "                avatarUrl: finalAvatarUrl,\n",
            "                avatarUrl: finalAvatarUrl,\n"
            "                backgroundUrl: finalBackgroundUrl,\n",
            2,
        )

    # Reassemble edit section.
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
# REMOTE GIF/IMAGE BACKGROUND VIEW
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

/// Full-screen remote background for the profile-selection screen.
///
/// Static images are displayed normally.
/// Multi-frame images, including GIFs, are decoded into an animated UIImage.
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

            // Static PNG/JPEG/etc.
            if frameCount == 1,
               let cgImage =
                CGImageSourceCreateImageAtIndex(
                    source,
                    0,
                    nil
                ) {

                return UIImage(cgImage: cgImage)
            }

            // Animated GIF / multi-frame image.
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

    text = path.read_text(encoding="utf-8")
    original = text

    if "<string>senplayer</string>" in text:
        print("plist: senplayer already present")
        return

    if "<string>outplayer</string>" not in text:
        fail(
            "could not find outplayer entry needed for SenPlayer support"
        )

    text = text.replace(
        "<string>outplayer</string>",
        "<string>senplayer</string>",
        1,
    )

    write_file(
        path,
        original,
        text,
        "plist",
    )


# ============================================================================
# MAIN
# ============================================================================

def main():

    if not SRC.exists():
        fail("NuvioMobile source missing")

    print()
    print("==============================================")
    print("Nuvio SenPlayer Profile GIF Background Patch")
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
    print("PROFILE_GIF_SENPLAYER_PATCH_OK")
    print("==============================================")
    print()


if __name__ == "__main__":
    main()
