import AppKit
import FramebaseDomain
import SwiftUI

struct FramebaseAssistantPanel: View {
    @Bindable var assistant: LibraryAssistantController

    private let quickPrompts: [(label: String, icon: String, prompt: String)] = [
        (
            "Blonde Hairlines Album",
            "rectangle.stack.badge.plus",
            "Create an album for me with all the hairline photos with color blonde hair"
        ),
        (
            "Undetectable Hairlines",
            "sparkles",
            "Show all strong undetectable hairline photos"
        ),
        (
            "Split Model Sub-Folders",
            "folder.badge.gearshape",
            "Split this model folder into headshots, editorial, and before-after"
        ),
        (
            "Repo & CRM Scout",
            "terminal",
            "Find open-source CRM and AI repo screenshots"
        ),
        (
            "Hair System Brain",
            "brain.head.profile",
            "Ask the Hair Concierge Brain: Swiss lace vs 0.03mm ultra-thin skin hairline graduation"
        )
    ]

    var body: some View {
        VStack(spacing: 0) {
            headerBar
            Divider()
            quickActionStrip
            Divider()
            messageScrollList
            if let status = assistant.statusBanner {
                HStack(spacing: 8) {
                    ProgressView()
                        .controlSize(.small)
                    Text(status)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.accentColor.opacity(0.08))
            }
            if assistant.attachedImageURL != nil || !assistant.windowModel.selectedAssetIDs.isEmpty {
                Divider()
                attachmentPreviewBar
            }
            Divider()
            composerBar
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: NSColor(srgbRed: 0.10, green: 0.10, blue: 0.115, alpha: 1.0)))
        .dropDestination(for: URL.self) { urls, _ in
            guard let first = urls.first else { return false }
            let ext = first.pathExtension.lowercased()
            guard ["png", "jpg", "jpeg", "webp", "heic", "tiff", "gif"].contains(ext) else { return false }
            assistant.attachImageURL(first)
            return true
        }
        .accessibilityIdentifier("assistant.panel")
    }

    private var headerBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "sparkles")
                .foregroundStyle(.tint)
            VStack(alignment: .leading, spacing: 1) {
                Text("Framebase 2.0 Media Expert")
                    .font(.headline)
                Text("The Hair Concierge Brain × Vertex AI Gemini 3.8 Flash")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
    }

    private var quickActionStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                Button {
                    Task {
                        await assistant.runMushroomHeadVisionDemo()
                    }
                } label: {
                    Label("Mushroom-Head Colors (Vision)", systemImage: "camera.viewfinder")
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(
                            RoundedRectangle(cornerRadius: 6)
                                .fill(Color.accentColor.opacity(0.22))
                        )
                }
                .buttonStyle(.plain)
                .disabled(assistant.isProcessing)
                .accessibilityIdentifier("assistant.chip.MushroomHeadVision")

                ForEach(quickPrompts, id: \.label) { chip in
                    Button {
                        Task {
                            await assistant.sendPrompt(chip.prompt)
                        }
                    } label: {
                        Label(chip.label, systemImage: chip.icon)
                            .font(.caption)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(Color.white.opacity(0.07))
                            )
                    }
                    .buttonStyle(.plain)
                    .disabled(assistant.isProcessing)
                    .accessibilityIdentifier("assistant.chip.\(chip.label)")
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
    }

    private var messageScrollList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(assistant.messages) { message in
                        messageBubble(message)
                            .id(message.id)
                    }
                }
                .padding(12)
            }
            .onChange(of: assistant.messages.count) {
                if let lastID = assistant.messages.last?.id {
                    withAnimation(.easeOut(duration: 0.2)) {
                        proxy.scrollTo(lastID, anchor: .bottom)
                    }
                }
            }
        }
    }

    private func messageBubble(_ message: AssistantMessage) -> some View {
        VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 6) {
            HStack {
                if message.role == .user { Spacer(minLength: 24) }
                VStack(alignment: .leading, spacing: 8) {
                    if let imgURL = message.attachedImageURL,
                       let nsImage = NSImage(contentsOf: imgURL) {
                        HStack(spacing: 8) {
                            Image(nsImage: nsImage)
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(maxWidth: 160, maxHeight: 110)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(Color.white.opacity(0.18), lineWidth: 1)
                                )
                            VStack(alignment: .leading, spacing: 2) {
                                Label("Reference Photo", systemImage: "camera.metering.matrix")
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(.secondary)
                                Text(imgURL.lastPathComponent)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                        }
                    }

                    Text(LocalizedStringKey(message.text))
                        .font(.callout)
                        .textSelection(.enabled)

                    if let card = message.actionCard {
                        actionCardView(card, messageID: message.id)
                    }
                }
                .padding(10)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(
                            message.role == .user
                                ? Color.accentColor.opacity(0.24)
                                : Color.white.opacity(0.06)
                        )
                )
                if message.role == .assistant { Spacer(minLength: 16) }
            }
        }
    }

    @ViewBuilder
    private func actionCardView(_ card: AssistantActionCard, messageID: UUID) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Divider()
            switch card.kind {
            case let .createdAlbum(_, albumName, assetIDs):
                HStack(spacing: 6) {
                    Image(systemName: "rectangle.stack.fill")
                        .foregroundStyle(.tint)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Album: \(albumName)")
                            .font(.caption.weight(.semibold))
                        Text("\(assetIDs.count) photos added")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                HStack(spacing: 8) {
                    Button("Open Album") {
                        assistant.performCardPrimaryAction(card)
                    }
                    .controlSize(.small)
                    .buttonStyle(.borderedProminent)
                    .disabled(card.isUndone)

                    if !card.isUndone {
                        Button("Undo") {
                            Task { await assistant.undoCardAction(messageID: messageID) }
                        }
                        .controlSize(.small)
                    }
                }

            case let .searchResults(title, querySummary, assetIDs):
                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass.circle.fill")
                        .foregroundStyle(.tint)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(assetIDs.count) Matching Assets")
                            .font(.caption.weight(.semibold))
                        Text(querySummary)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                if !assetIDs.isEmpty {
                    HStack(spacing: 8) {
                        Button("Select in Browser") {
                            assistant.performCardPrimaryAction(card)
                        }
                        .controlSize(.small)

                        Button("Create Album \"\(title)\"") {
                            Task {
                                await assistant.sendPrompt("Create an album called \"\(title)\" with \(querySummary)")
                            }
                        }
                        .controlSize(.small)
                        .buttonStyle(.borderedProminent)
                    }
                }

            case let .organizedSubfolders(_, parentName, movedBySubfolder, _):
                HStack(spacing: 6) {
                    Image(systemName: "folder.fill.badge.gearshape")
                        .foregroundStyle(.tint)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Organized \(parentName)")
                            .font(.caption.weight(.semibold))
                        Text("\(movedBySubfolder.count) specialist sub-folders updated")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                HStack(spacing: 8) {
                    Button("Reveal Folder") {
                        assistant.performCardPrimaryAction(card)
                    }
                    .controlSize(.small)
                    .buttonStyle(.borderedProminent)

                    if !card.isUndone {
                        Button("Undo Split") {
                            Task { await assistant.undoCardAction(messageID: messageID) }
                        }
                        .controlSize(.small)
                    }
                }

            case let .knowledgeRepos(items):
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(items.prefix(4)) { item in
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: "chevron.left.forwardslash.chevron.right")
                                .font(.caption2)
                                .foregroundStyle(.tint)
                                .padding(.top, 2)
                            VStack(alignment: .leading, spacing: 1) {
                                Text("\(item.name) · \(item.category)")
                                    .font(.caption.weight(.semibold))
                                Text(item.summary)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)
                            }
                        }
                    }
                }
            }

            if !card.focusOptions.isEmpty {
                Divider()
                VStack(alignment: .leading, spacing: 5) {
                    Text("Click an option to focus your similar image search:")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)

                    ForEach(card.focusOptions) { opt in
                        Button {
                            Task {
                                await assistant.runFocusOption(opt)
                            }
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "sparkle.magnifyingglass")
                                    .font(.caption2)
                                    .foregroundStyle(.tint)
                                Text(opt.label)
                                    .font(.caption)
                                    .multilineTextAlignment(.leading)
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            .padding(.horizontal, 8)
                            .padding(.vertical, 5)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(Color.white.opacity(0.08))
                            )
                        }
                        .buttonStyle(.plain)
                        .disabled(assistant.isProcessing)
                    }
                }
            }
        }
        .padding(8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.black.opacity(0.22))
        )
    }

    @ViewBuilder
    private var attachmentPreviewBar: some View {
        HStack(spacing: 8) {
            if let url = assistant.attachedImageURL {
                if let nsImg = NSImage(contentsOf: url) {
                    Image(nsImage: nsImg)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: 36, height: 36)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                } else {
                    Image(systemName: "photo.fill")
                        .foregroundStyle(.tint)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text(url.lastPathComponent)
                        .font(.caption.weight(.semibold))
                        .lineLimit(1)
                    Text("Vertex AI Gemini 3.8 Flash Vision Ready")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    assistant.clearAttachment()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .help("Remove attached photo")
            } else if !assistant.windowModel.selectedAssetIDs.isEmpty {
                Image(systemName: "photo.on.rectangle.angled")
                    .foregroundStyle(.tint)
                Text("1 selected browser photo available for Vision search")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Attach Selected") {
                    assistant.attachSelectedLibraryAsset()
                }
                .controlSize(.mini)
                .buttonStyle(.bordered)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Color.white.opacity(0.04))
    }

    private var composerBar: some View {
        HStack(spacing: 8) {
            Button {
                assistant.pickImageAttachment()
            } label: {
                Image(systemName: assistant.attachedImageURL != nil ? "photo.badge.checkmark.fill" : "photo.badge.plus")
                    .font(.title3)
                    .foregroundStyle(assistant.attachedImageURL != nil ? Color.accentColor : Color.secondary)
            }
            .buttonStyle(.plain)
            .help("Upload or attach a reference photo for Vision similarity search")
            .disabled(assistant.isProcessing)
            .accessibilityIdentifier("assistant.uploadPhoto")

            TextField(
                "Upload a photo (+) or ask Framebase AI (e.g. 'Find all mushroom-head hair colors')…",
                text: $assistant.inputText
            )
            .textFieldStyle(.roundedBorder)
            .onSubmit {
                Task { await assistant.sendPrompt() }
            }
            .accessibilityIdentifier("assistant.input")

            Button {
                Task { await assistant.sendPrompt() }
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.title3)
            }
            .buttonStyle(.plain)
            .disabled((assistant.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && assistant.attachedImageURL == nil) || assistant.isProcessing)
            .accessibilityIdentifier("assistant.send")
        }
        .padding(10)
    }
}

