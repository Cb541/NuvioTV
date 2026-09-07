#!/usr/bin/env python3
from pathlib import Path
import re, sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'NuvioMobile'

def fail(msg):
    print('ERROR:', msg, file=sys.stderr); raise SystemExit(1)

def find_file(name, contains=None):
    hits=[]
    for p in SRC.rglob(name):
        try: t=p.read_text(encoding='utf-8')
        except: continue
        if contains is None or contains in t: hits.append(p)
    if not hits: fail(f'could not find {name}')
    if len(hits)>1: print(f'WARN: multiple {name}; using {hits[0]}')
    return hits[0]

def insert_after_once(text, needle, repl, label):
    if repl in text: return text, False
    if needle not in text: fail(f'missing marker for {label}: {needle}')
    return text.replace(needle, needle + repl, 1), True

def patch_models():
    p = SRC/'shared/src/commonMain/kotlin/com/nuvio/app/features/profiles/ProfileModels.kt'
    if not p.exists(): fail(f'missing {p}')
    t=p.read_text()
    changed=False
    for marker in [
        '@SerialName("avatar_url") val avatarUrl: String? = null,\n',
    ]:
        count=t.count(marker)
        if count<2: fail(f'expected 2 avatar_url fields in ProfileModels.kt, found {count}')
        t2=t.replace(marker, marker+'    @SerialName("background_url") val backgroundUrl: String? = null,\n')
        changed |= t2!=t; t=t2
        break
    if 'fun normalizedProfileBackgroundUrl' not in t:
        helper='''\nfun normalizedProfileBackgroundUrl(url: String?): String? =\n    url?.trim()?.takeIf { it.isValidRemoteImageUrl() }\n\nprivate fun String.isValidRemoteImageUrl(): Boolean {\n    val value = trim()\n    return value.length <= 2048 &&\n        !value.any { it.isWhitespace() } &&\n        (value.startsWith("https://") || value.startsWith("http://"))\n}\n\nfun profileBackgroundImageUrl(profile: NuvioProfile): String? =\n    normalizedProfileBackgroundUrl(profile.backgroundUrl)\n'''
        t += helper; changed=True
    if changed: p.write_text(t)
    print('models:', 'patched' if changed else 'already patched')

def patch_repository():
    p=SRC/'shared/src/commonMain/kotlin/com/nuvio/app/features/profiles/ProfileRepository.kt'
    if not p.exists(): fail(f'missing {p}')
    t=p.read_text(); original=t; changed=False
    # Add parameter to create/update functions only.
    for fname in ('createProfile','updateProfile'):
        m=re.search(rf'(suspend fun {fname}\s*\([^)]*?avatarUrl\s*:\s*String\?\s*=\s*null,)(?!\s*backgroundUrl)', t, re.S)
        if not m:
            print('WARN: signature marker not found or already patched:', fname)
        else:
            t=t[:m.end(1)]+'\n        backgroundUrl: String? = null,'+t[m.end(1):]
            changed=True
    # Propagate backgroundUrl through ProfilePushPayload constructors.
    def payload_repl(m):
        block=m.group(0)
        if 'backgroundUrl =' in block: return block
        av=re.search(r'(?m)^(\s*)avatarUrl\s*=\s*([^,]+),', block)
        if not av: return block
        expr=av.group(2).strip()
        bg_expr={
            'profile.avatarUrl':'profile.backgroundUrl',
            'avatarUrl':'backgroundUrl',
            'payload.avatarUrl':'payload.backgroundUrl',
        }.get(expr)
        if not bg_expr:
            return block
        indent=av.group(1)
        return block[:av.end()]+f'\n{indent}backgroundUrl = {bg_expr},'+block[av.end():]
    t2=re.sub(r'ProfilePushPayload\s*\([^)]*\)', payload_repl, t, flags=re.S)
    changed |= t2!=t; t=t2
    if t==original and 'backgroundUrl' not in t: fail('repository patch made no changes')
    p.write_text(t)
    print('repository: patched')

def patch_viewmodel():
    p=find_file('ProfilesViewModel.swift', 'class ProfilesViewModel')
    t=p.read_text(); original=t
    # Public wrapper signatures.
    t,n1=re.subn(r'(func createProfile\s*\([^)]*?avatarUrl\s*:\s*String\?,)(?!\s*backgroundUrl)', r'\1\n        backgroundUrl: String? = nil,', t, flags=re.S, count=1)
    t,n2=re.subn(r'(func updateProfile\s*\([^)]*?avatarUrl\s*:\s*String\?,)(?!\s*backgroundUrl)', r'\1\n        backgroundUrl: String? = nil,', t, flags=re.S, count=1)
    # Repository calls: add backgroundUrl after avatarUrl: avatarUrl.
    t=t.replace('avatarUrl: avatarUrl,\n', 'avatarUrl: avatarUrl,\n            backgroundUrl: backgroundUrl,\n')
    p.write_text(t)
    print('viewmodel:', 'patched' if t!=original else 'already patched', 'signatures', n1+n2)

def patch_swift_view():
    p=SRC/'iosApp/NuvioTV/Screens/ProfileSelectionView.swift'
    if not p.exists(): fail(f'missing {p}')
    t=p.read_text(); original=t
    # Add animated background above the existing theme background.
    marker='        ZStack {\n            Theme.Palette.background.ignoresSafeArea()'
    replacement='''        ZStack {\n            if let backgroundURL = profileSelectionBackgroundURL {\n                ProfileSelectionRemoteAnimatedImage(urlString: backgroundURL)\n                    .ignoresSafeArea()\n            }\n            Theme.Palette.background.ignoresSafeArea()\n'''
    if 'profileSelectionBackgroundURL' not in t:
        t=t.replace(marker, replacement, 1)
        # property inside ProfileSelectionView
        vm='''\n    private var profileSelectionBackgroundURL: String? {\n        let profile = model.activeProfile ?? model.profiles.first\n        return profile.flatMap { ProfileModelsKt.profileBackgroundImageUrl(profile: $0) }\n    }\n'''
        t=t.replace('    var body: some View {', vm+'    var body: some View {', 1)
    # Edit screen state + initializer.
    if '@State private var backgroundUrl: String' not in t:
        t=t.replace('    @State private var avatarId: String?\n', '    @State private var avatarId: String?\n    @State private var backgroundUrl: String\n', 1)
        t=t.replace('        _avatarId = State(initialValue: target.profile?.avatarId)\n', '        _avatarId = State(initialValue: target.profile?.avatarId)\n        _backgroundUrl = State(initialValue: target.profile?.backgroundUrl ?? "")\n', 1)
    # Add text field after Name.
    if 'Custom background URL' not in t:
        marker='''                     TextField("Name", text: $name)\n                         .textFieldStyle(.plain)\n                         .font(Theme.Font.body)\n                         .foregroundStyle(Theme.Palette.textPrimary)\n                         .padding(Theme.Spacing.lg)\n                         .frame(maxWidth: 700)\n                         .glassEffect(.regular, in: RoundedRectangle(cornerRadius: Theme.Radius.card))\n'''
        field=marker+'''                     TextField("Custom background URL", text: $backgroundUrl)\n                         .textFieldStyle(.plain)\n                         .font(Theme.Font.body)\n                         .foregroundStyle(Theme.Palette.textPrimary)\n                         .padding(Theme.Spacing.lg)\n                         .frame(maxWidth: 700)\n                         .glassEffect(.regular, in: RoundedRectangle(cornerRadius: Theme.Radius.card))\n                         .accessibilityLabel(String(localized: "Profile selection background URL"))\n'''
        if marker not in t: fail('name field marker not found')
        t=t.replace(marker, field, 1)
    # Pass value into create/update.
    t=t.replace('                avatarUrl: finalAvatarUrl\n', '                avatarUrl: finalAvatarUrl,\n                backgroundUrl: sanitizedBackgroundUrl\n', 1)
    t=t.replace('                avatarUrl: finalAvatarUrl\n', '                avatarUrl: finalAvatarUrl,\n                backgroundUrl: sanitizedBackgroundUrl\n', 1)
    if 'let sanitizedBackgroundUrl' not in t:
        marker='''        if let profile = target.profile {\n'''
        ins='''        let sanitizedBackgroundUrl = backgroundUrl.trimmingCharacters(in: .whitespacesAndNewlines)\n            .prefix(2048)\n            .description\n        let finalBackgroundUrl = sanitizedBackgroundUrl.isEmpty ? nil : sanitizedBackgroundUrl\n        if let profile = target.profile {\n'''
        # Replace calls to use finalBackgroundUrl, not a nonoptional string.
        t=t.replace(marker, ins, 1)
        t=t.replace('backgroundUrl: sanitizedBackgroundUrl', 'backgroundUrl: finalBackgroundUrl')
    p.write_text(t)
    print('profile view:', 'patched' if t!=original else 'already patched')

def add_remote_image_file():
    p=SRC/'iosApp/NuvioTV/Screens/ProfileSelectionRemoteAnimatedImage.swift'
    if p.exists(): return
    code='''import SwiftUI\nimport UIKit\nimport ImageIO\n\n/// Full-screen remote image used specifically for the profile-selection backdrop.\n/// Static images are supported too; GIFs are decoded into an animated UIImage.\nstruct ProfileSelectionRemoteAnimatedImage: View {\n    let urlString: String\n    @State private var image: UIImage?\n\n    var body: some View {\n        Group {\n            if let image {\n                Image(uiImage: image)\n                    .resizable()\n                    .scaledToFill()\n            } else {\n                Color.clear\n            }\n        }\n        .frame(maxWidth: .infinity, maxHeight: .infinity)\n        .clipped()\n        .overlay(Color.black.opacity(0.34))\n        .allowsHitTesting(false)\n        .task(id: urlString) {\n            image = await load(urlString)\n        }\n    }\n\n    private func load(_ value: String) async -> UIImage? {\n        let raw = value.trimmingCharacters(in: .whitespacesAndNewlines)\n        guard raw.count <= 2048,\n              !raw.contains(where: { $0.isWhitespace }),\n              let url = URL(string: raw),\n              let scheme = url.scheme?.lowercased(),\n              scheme == "http" || scheme == "https" else { return nil }\n        do {\n            let (data, response) = try await URLSession.shared.data(from: url)\n            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) { return nil }\n            guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }\n            let count = CGImageSourceGetCount(source)\n            guard count > 0 else { return nil }\n            if count == 1, let cg = CGImageSourceCreateImageAtIndex(source, 0, nil) {\n                return UIImage(cgImage: cg)\n            }\n            var frames: [UIImage] = []\n            var duration: Double = 0\n            for i in 0..<count {\n                guard let cg = CGImageSourceCreateImageAtIndex(source, i, nil) else { continue }\n                frames.append(UIImage(cgImage: cg))\n                if let props = CGImageSourceCopyPropertiesAtIndex(source, i, nil) as? [CFString: Any],\n                   let gif = props[kCGImagePropertyGIFDictionary] as? [CFString: Any],\n                   let d = (gif[kCGImagePropertyGIFUnclampedDelayTime] ?? gif[kCGImagePropertyGIFDelayTime]) as? Double {\n                    duration += max(d, 0.02)\n                } else {\n                    duration += 0.1\n                }\n            }\n            guard !frames.isEmpty else { return nil }\n            return UIImage.animatedImage(with: frames, duration: max(duration, 0.1))\n        } catch {\n            return nil\n        }\n    }\n}\n'''
    p.write_text(code)

def patch_plist():
    p=SRC/'iosApp/NuvioTV/Info.plist'
    if not p.exists(): fail('missing tvOS Info.plist')
    t=p.read_text()
    # Preserve the user's SenPlayer modification exactly: replace Outplayer allowlist entry.
    if '<string>senplayer</string>' not in t:
        if '<string>outplayer</string>' in t:
            t=t.replace('<string>outplayer</string>', '<string>senplayer</string>', 1)
        else:
            fail('could not find outplayer entry to preserve SenPlayer modification')
        p.write_text(t)
        print('plist: outplayer -> senplayer')
    else: print('plist: senplayer already present')

def main():
    if not SRC.exists(): fail('NuvioMobile source missing')
    patch_models(); patch_repository(); patch_viewmodel(); patch_swift_view(); add_remote_image_file(); patch_plist()
    print('PROFILE_GIF_SENPLAYER_PATCH_OK')

if __name__=='__main__': main()
