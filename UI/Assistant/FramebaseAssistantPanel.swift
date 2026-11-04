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
            Divider()
            composerBar
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: NSColor(srgbRed: 0.10, green: 0.10, blue: 0.115, alpha: 1.0)))
        .accessibilityIdentifier("assistant.panel")
    }

    private var headerBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "sparkles")
                .foregroundStyle(.tint)
            VStack(alignment: .leading, spacing: 1) {
                Text("Framebase 2.0 Media Expert")
                    .font(.headline)
                Text("Cloudflare Agents SDK × Gemini 3.8 Flash")
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
        }
        .padding(8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.black.opacity(0.22))
        )
    }

    private var composerBar: some View {
        HStack(spacing: 8) {
            TextField(
                "Ask Framebase AI (e.g. 'Create an album with all blonde hairline photos')…",
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
            .disabled(assistant.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || assistant.isProcessing)
            .accessibilityIdentifier("assistant.send")
        }
        .padding(10)
    }
}

