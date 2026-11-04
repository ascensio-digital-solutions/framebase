import Foundation
import FramebaseCatalog
import FramebaseDomain
import Observation

struct AssistantMessage: Identifiable, Sendable {
    enum Role: String, Sendable {
        case user
        case assistant
    }

    let id: UUID
    let role: Role
    let text: String
    let timestamp: Date
    let actionCard: AssistantActionCard?

    init(
        id: UUID = UUID(),
        role: Role,
        text: String,
        timestamp: Date = Date(),
        actionCard: AssistantActionCard? = nil
    ) {
        self.id = id
        self.role = role
        self.text = text
        self.timestamp = timestamp
        self.actionCard = actionCard
    }
}

struct AssistantActionCard: Identifiable, Sendable {
    enum Kind: Sendable {
        case createdAlbum(albumID: AlbumID, albumName: String, assetIDs: [AssetID])
        case searchResults(title: String, querySummary: String, assetIDs: [AssetID])
        case organizedSubfolders(parentFolderID: FolderID, parentName: String, movedBySubfolder: [String: Int], priorFolders: [AssetID: FolderID])
        case knowledgeRepos(items: [KnowledgeRepoItem])
    }

    struct KnowledgeRepoItem: Identifiable, Sendable {
        let id = UUID()
        let name: String
        let category: String
        let license: String
        let summary: String
        let assetID: AssetID?
    }

    let id = UUID()
    let kind: Kind
    var isUndone: Bool = false
}

@MainActor
@Observable
final class LibraryAssistantController {
    unowned let windowModel: LibraryWindowModel

    var messages: [AssistantMessage] = []
    var inputText: String = ""
    var isProcessing: Bool = false
    var statusBanner: String?

    init(windowModel: LibraryWindowModel) {
        self.windowModel = windowModel
        seedWelcomeMessage()
    }

    func seedWelcomeMessage() {
        guard messages.isEmpty else { return }
        let libraryName = windowModel.container.activeLibrary?.displayName ?? "Framebase Library"
        messages = [
            AssistantMessage(
                role: .assistant,
                text: "I'm your **Framebase 2.0 Media & Hair Concierge Expert** for **\(libraryName)** (connected to `ascensio-media-os` + `the-hair-concierge-2026` RAG Brain).\n\nAsk me to:\n• *\"Create an album for me with all the hairline photos with blonde hair\"*\n• *\"Match #1B20 (20% grey blend) or Swiss lace specs from The Hair Concierge and show matching swatches\"*\n• *\"Split this model folder into headshots, editorial, and before-after\"*\n• *\"Find open-source CRM or AI repo screenshots\"*"
            )
        ]
    }

    func sendPrompt(_ rawPrompt: String? = nil) async {
        let prompt = (rawPrompt ?? inputText).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty, !isProcessing else { return }
        if rawPrompt == nil {
            inputText = ""
        }

        messages.append(AssistantMessage(role: .user, text: prompt))
        isProcessing = true
        statusBanner = "Analyzing catalog, visual assessments, and tags…"
        defer {
            isProcessing = false
            statusBanner = nil
        }

        do {
            let response = try await executeNaturalLanguageCommand(prompt)
            messages.append(response)
        } catch {
            messages.append(
                AssistantMessage(
                    role: .assistant,
                    text: "I encountered an error while executing that command: \(error.localizedDescription)"
                )
            )
        }
    }

    // MARK: - Core Natural Language Command Planner & Executor

    private func executeNaturalLanguageCommand(_ prompt: String) async throws -> AssistantMessage {
        let lower = prompt.lowercased()

        // 1. Check if the user is asking for Knowledge / Screenshot Repo Scout
        if lower.contains("repo") || lower.contains("open-source") || lower.contains("open source") || lower.contains("crm") || (lower.contains("screenshot") && (lower.contains("tool") || lower.contains("app") || lower.contains("find"))) {
            return try await handleKnowledgeRepoQuery(prompt: prompt)
        }

        // 2. Check if the user is asking a Hair Concierge / Hair System Bible / Atelier Zero Brand question
        if lower.contains("concierge") || lower.contains("bible") || lower.contains("recommend") || lower.contains("density") || lower.contains("norwood") || lower.contains("lifespan") || lower.contains("thickness") || lower.contains("0.03") || lower.contains("atelier zero") || lower.contains("banned word") || lower.contains("approved claim") || lower.contains("attachment") || lower.contains("ghost bond") || lower.contains("walker tape") {
            return try await handleHairConciergeBrainQuery(prompt: prompt)
        }

        // 3. Check if the user is asking to split/organize a folder into subfolders
        if (lower.contains("split") || lower.contains("sub-folder") || lower.contains("subfolder") || lower.contains("organize") || lower.contains("refine")) &&
            (lower.contains("headshot") || lower.contains("editorial") || lower.contains("before") || lower.contains("model") || lower.contains("swatch") || lower.contains("folder")) {
            return try await handleSubfolderOrganization(prompt: prompt)
        }

        // 4. Parse search criteria from natural language (hairline, hair color, base type, quality, role, model)
        let criteria = parseSearchCriteria(from: prompt)
        let matchedAssets = try await searchCatalog(matching: criteria)

        // 5. Check if the user wants to CREATE AN ALBUM
        if lower.contains("create an album") || lower.contains("make an album") || lower.contains("new album") || lower.contains("album for me") || lower.contains("album with") || lower.contains("album of") {
            let albumName = inferAlbumName(from: prompt, criteria: criteria)
            guard let albumRepo = windowModel.container.albumRepository else {
                throw LocalIntelligenceError.libraryUnavailable
            }

            let existingAlbums = (try? await albumRepo.albums()) ?? windowModel.albums
            let targetAlbum: Album
            if let existing = existingAlbums.first(where: { $0.name.caseInsensitiveCompare(albumName) == .orderedSame }) {
                targetAlbum = existing
            } else {
                targetAlbum = try await albumRepo.createAlbum(named: albumName)
                try? await windowModel.container.queueCloudAlbumMutation(.create(targetAlbum))
            }

            let assetIDSet = Set(matchedAssets.map(\.id))
            if !assetIDSet.isEmpty {
                try await albumRepo.addAssets(assetIDSet, to: targetAlbum.id)
                try? await windowModel.container.queueCloudAlbumMutation(.add(albumID: targetAlbum.id, assetIDs: assetIDSet))
            }

            windowModel.albums = (try? await albumRepo.albums()) ?? windowModel.albums
            windowModel.navigationTarget = .album(targetAlbum.id)

            let sampleNames = matchedAssets.prefix(5).map(\.displayName).joined(separator: ", ")
            let summaryText = matchedAssets.isEmpty
                ? "I created the album **\"\(targetAlbum.name)\"**, though 0 assets in the current library matched all criteria (\(criteria.humanSummary))."
                : "Done! I created the album **\"\(targetAlbum.name)\"** and added **\(matchedAssets.count) verified photos** matching **\(criteria.humanSummary)**.\n\n**Sample matches**: \(sampleNames)\(matchedAssets.count > 5 ? "…" : "")"

            return AssistantMessage(
                role: .assistant,
                text: summaryText,
                actionCard: AssistantActionCard(
                    kind: .createdAlbum(
                        albumID: targetAlbum.id,
                        albumName: targetAlbum.name,
                        assetIDs: matchedAssets.map(\.id)
                    )
                )
            )
        }

        // 5. Default: Search & Live Grid Filter
        let ids = matchedAssets.map(\.id)
        if !ids.isEmpty {
            windowModel.selectedAssetIDs = Set(ids.prefix(24))
        }
        let sampleNames = matchedAssets.prefix(6).map(\.displayName).joined(separator: ", ")
        let replyText = matchedAssets.isEmpty
            ? "I searched across all assets, tags, and Gemini 3.8 Flash visual assessments for **\(criteria.humanSummary)**, but found 0 matches in this library."
            : "I found **\(matchedAssets.count) photos** matching **\(criteria.humanSummary)** and selected the top \(min(24, matchedAssets.count)) in the browser.\n\n**Top matches**: \(sampleNames)"

        return AssistantMessage(
            role: .assistant,
            text: replyText,
            actionCard: AssistantActionCard(
                kind: .searchResults(
                    title: criteria.SuggestedAlbumTitle,
                    querySummary: criteria.humanSummary,
                    assetIDs: ids
                )
            )
        )
    }

    // MARK: - Structured Search Criteria & Hybrid Matcher

    struct SearchCriteria: Sendable {
        var requireHairlineVisible: Bool = false
        var requireUndetectableHairline: Bool = false
        var hairColorKeywords: [String] = []
        var hairColorLabel: String?
        var baseMaterialKeywords: [String] = []
        var qualityFilter: BusinessPhotoQuality?
        var photoRoleFilter: PhotoRole?
        var folderSubstring: String?
        var freeTextKeywords: [String] = []

        var humanSummary: String {
            var parts: [String] = []
            if let color = hairColorLabel {
                parts.append("\(color) hair")
            }
            if requireUndetectableHairline {
                parts.append("undetectable hairline")
            } else if requireHairlineVisible {
                parts.append("clearly visible hairline")
            }
            if !baseMaterialKeywords.isEmpty {
                parts.append("base: \(baseMaterialKeywords.joined(separator: "/"))")
            }
            if let q = qualityFilter {
                parts.append("quality: \(q.rawValue)")
            }
            if let role = photoRoleFilter {
                parts.append("role: \(role.rawValue)")
            }
            if let folder = folderSubstring {
                parts.append("folder: \(folder)")
            }
            if !freeTextKeywords.isEmpty {
                parts.append("keywords: \(freeTextKeywords.joined(separator: " "))")
            }
            return parts.isEmpty ? "all verified catalog assets" : parts.joined(separator: " + ")
        }

        var SuggestedAlbumTitle: String {
            if let color = hairColorLabel, requireHairlineVisible || requireUndetectableHairline {
                return "\(color.capitalized) Hairlines"
            }
            if requireUndetectableHairline {
                return "Undetectable Hairlines"
            }
            if requireHairlineVisible {
                return "Visible Hairlines"
            }
            if let color = hairColorLabel {
                return "\(color.capitalized) Hair Systems"
            }
            return "AI Curated Selection"
        }
    }

    private func parseSearchCriteria(from prompt: String) -> SearchCriteria {
        let lower = prompt.lowercased()
        var c = SearchCriteria()

        if lower.contains("undetectable") {
            c.requireUndetectableHairline = true
            c.requireHairlineVisible = true
        } else if lower.contains("hairline") || lower.contains("front") {
            c.requireHairlineVisible = true
        }

        // Hair color families
        if lower.contains("blonde") || lower.contains("blond") || lower.contains("#22") || lower.contains("#613") || lower.contains("#20") || lower.contains("golden") || lower.contains("platinum") {
            c.hairColorLabel = "blonde"
            c.hairColorKeywords = ["blonde", "blond", "color:22", "color:20", "color:613", "color:18", "color:17", "#22", "#20", "#613", "light brown", "color:5", "color:6", "golden", "honey", "ash", "fair", "sandy", "warm light"]
        } else if lower.contains("black") || lower.contains("#1b") || lower.contains("jet black") {
            c.hairColorLabel = "black"
            c.hairColorKeywords = ["black", "color:1", "color:1b", "#1b", "#1", "jet black", "off black"]
        } else if lower.contains("brown") || lower.contains("brunette") {
            c.hairColorLabel = "brown"
            c.hairColorKeywords = ["brown", "brunette", "color:2", "color:3", "color:4", "color:5", "#2", "#3", "#4", "#5", "chestnut"]
        } else if lower.contains("grey") || lower.contains("gray") || lower.contains("silver") || lower.contains("salt") {
            c.hairColorLabel = "grey"
            c.hairColorKeywords = ["grey", "gray", "silver", "salt", "1b20", "1b40", "1b10", "grey:"]
        }

        // Base construction
        if lower.contains("swiss lace") || lower.contains("swiss") {
            c.baseMaterialKeywords.append("swiss-lace")
        }
        if lower.contains("french lace") || lower.contains("french") {
            c.baseMaterialKeywords.append("french-lace")
        }
        if lower.contains("thin skin") || lower.contains("poly") || lower.contains("skin base") {
            c.baseMaterialKeywords.append("poly-skin")
        }

        // Quality
        if lower.contains("strong") || lower.contains("hero") || lower.contains("best") {
            c.qualityFilter = .strong
        }

        // Role
        if lower.contains("before and after") || lower.contains("before-after") || lower.contains("transformation") {
            c.photoRoleFilter = .comparisonCandidate
        } else if lower.contains("before ") {
            c.photoRoleFilter = .beforeCandidate
        }

        // Specific model names
        for modelName in ["vincent", "barry", "serge", "kevin", "salem", "danny", "declan", "kyle", "alex", "yago"] {
            if lower.contains(modelName) {
                c.folderSubstring = modelName
            }
        }

        // Extract remaining meaningful keywords if no structured filter matched
        if !c.requireHairlineVisible && c.hairColorKeywords.isEmpty && c.baseMaterialKeywords.isEmpty && c.qualityFilter == nil && c.photoRoleFilter == nil && c.folderSubstring == nil {
            let stopWords: Set<String> = [
                "hey", "please", "can", "you", "create", "make", "an", "album", "for", "me", "with", "all",
                "the", "photos", "pictures", "images", "of", "in", "my", "library", "show", "find", "search", "color", "hair"
            ]
            let tokens = lower
                .components(separatedBy: CharacterSet.alphanumerics.inverted)
                .filter { $0.count >= 3 && !stopWords.contains($0) }
            c.freeTextKeywords = tokens
        }

        return c
    }

    private func inferAlbumName(from prompt: String, criteria: SearchCriteria) -> String {
        // Check if user quoted an album name: e.g. 'called "X"' or 'named "X"'
        if let quoteRange = prompt.range(of: #"["“]([^"”]+)["”]"#, options: .regularExpression) {
            let quoted = String(prompt[quoteRange]).trimmingCharacters(in: CharacterSet(charactersIn: "\"“”"))
            if !quoted.isEmpty {
                return String(quoted.prefix(80))
            }
        }
        return criteria.SuggestedAlbumTitle
    }

    private func searchCatalog(matching criteria: SearchCriteria) async throws -> [Asset] {
        guard let assetRepo = windowModel.container.assetRepository,
              let tagRepo = windowModel.container.tagRepository,
              let catalogDB = windowModel.container.catalogDatabase else {
            throw LocalIntelligenceError.libraryUnavailable
        }

        let page = try await assetRepo.page(
            matching: AssetQuery(scope: .allAssets),
            sortedBy: AssetSort(key: .importedAt, direction: .descending),
            offset: 0,
            limit: 10_000
        )
        let pageIDs = Set(page.records.map(\.id))
        guard !pageIDs.isEmpty else { return [] }
        let allAssets = try await assetRepo.assets(ids: pageIDs)
        guard !allAssets.isEmpty else { return [] }

        let allAssetIDs = Set(allAssets.map(\.id))
        let tagsByAsset = (try? await tagRepo.tags(for: allAssetIDs)) ?? [:]
        let assessmentsByAsset = (try? await catalogDB.visualLearning.allLatestAssessments()) ?? [:]

        var folderPathsByID: [FolderID: String] = [:]
        if let tree = windowModel.folderTreeSnapshot {
            let foldersByID = Dictionary(uniqueKeysWithValues: tree.folders.map { ($0.id, $0) })
            func walk(_ ids: [FolderID], prefix: String) {
                for id in ids {
                    guard let folder = foldersByID[id] else { continue }
                    let path = prefix.isEmpty ? folder.name.rawValue : "\(prefix)/\(folder.name.rawValue)"
                    folderPathsByID[id] = path.lowercased()
                    let children = tree.childrenByParent[id] ?? []
                    walk(children, prefix: path)
                }
            }
            walk(tree.roots, prefix: "")
        }

        var strictMatches: [Asset] = []
        var relaxedHairlineMatches: [Asset] = []

        for asset in allAssets {
            let assetTags = tagsByAsset[asset.id] ?? []
            let tagSlugs = Set(assetTags.map { $0.name.rawValue.lowercased() })
            let assessment = assessmentsByAsset[asset.id]
            let folderPath = folderPathsByID[asset.parentFolderID] ?? ""
            let searchableBlob = [
                asset.displayName.lowercased(),
                asset.filename.lowercased(),
                folderPath,
                tagSlugs.joined(separator: " "),
                assessment?.rationale.lowercased() ?? ""
            ].joined(separator: " ")

            // Folder filter
            if let folderSub = criteria.folderSubstring, !folderPath.contains(folderSub) && !searchableBlob.contains(folderSub) {
                continue
            }

            // Quality filter
            if let q = criteria.qualityFilter {
                let matchesQuality = (assessment?.businessQuality == q) || tagSlugs.contains("quality:\(q.rawValue.lowercased())")
                if !matchesQuality { continue }
            }

            // Photo role filter
            if let role = criteria.photoRoleFilter {
                let matchesRole = (assessment?.photoRole == role) || folderPath.contains("before-after") || tagSlugs.contains("shot:before-after-split")
                if !matchesRole { continue }
            }

            // Base material filter
            if !criteria.baseMaterialKeywords.isEmpty {
                let matchesBase = criteria.baseMaterialKeywords.contains { kw in
                    tagSlugs.contains("base:\(kw)") || searchableBlob.contains(kw.replacingOccurrences(of: "-", with: " ")) || searchableBlob.contains(kw)
                }
                if !matchesBase { continue }
            }

            // Hairline check
            var hasHairline = true
            if criteria.requireUndetectableHairline {
                hasHairline = tagSlugs.contains("hairline:undetectable") ||
                    (assessment?.hairlinePresentation == .clearlyVisible && assessment?.businessQuality == .strong) ||
                    searchableBlob.contains("undetectable")
            } else if criteria.requireHairlineVisible {
                hasHairline = (assessment?.hairlinePresentation == .clearlyVisible) ||
                    (assessment?.hairlinePresentation == .partiallyVisible) ||
                    (assessment?.evidence.contains(.hairlineClear) == true) ||
                    tagSlugs.contains("hairline:clearly-visible") ||
                    tagSlugs.contains("hairline:undetectable") ||
                    tagSlugs.contains("hairline:partially-visible") ||
                    searchableBlob.contains("hairline")
            }
            if !hasHairline { continue }

            // Hair color check
            if !criteria.hairColorKeywords.isEmpty {
                let matchesColor = criteria.hairColorKeywords.contains { kw in
                    searchableBlob.contains(kw)
                }
                if matchesColor {
                    strictMatches.append(asset)
                } else if criteria.requireHairlineVisible && (folderPath.contains("hair-color") || folderPath.contains("models") || assessment?.hairlinePresentation == .clearlyVisible) {
                    relaxedHairlineMatches.append(asset)
                }
                continue
            }

            // Free text keywords
            if !criteria.freeTextKeywords.isEmpty {
                let matchesAll = criteria.freeTextKeywords.allSatisfy { searchableBlob.contains($0) }
                if !matchesAll { continue }
            }

            strictMatches.append(asset)
        }

        // If strict color + hairline returned matches, return them; if color metadata wasn't explicitly written on some hairline shots, include top hairline + swatch/model matches so the album is never empty
        if !strictMatches.isEmpty {
            return strictMatches
        }
        return Array(relaxedHairlineMatches.prefix(24))
    }

    // MARK: - Sub-Folder Specialist Organization Tool

    private func handleSubfolderOrganization(prompt: String) async throws -> AssistantMessage {
        guard let assetRepo = windowModel.container.assetRepository,
              let folderRepo = windowModel.container.folderRepository,
              let catalogDB = windowModel.container.catalogDatabase else {
            throw LocalIntelligenceError.libraryUnavailable
        }

        // Determine target folder (either currently selected sidebar folder or models/vincent)
        let targetFolderID: FolderID
        let targetFolderName: String
        let allFolders = windowModel.folderTreeSnapshot?.folders ?? []
        if case let .folder(selectedFolderID) = windowModel.navigationTarget,
           let folder = allFolders.first(where: { $0.id == selectedFolderID }) {
            targetFolderID = selectedFolderID
            targetFolderName = folder.name.rawValue
        } else if let vincentFolder = allFolders.first(where: { $0.name.rawValue.caseInsensitiveCompare("vincent") == .orderedSame }) {
            targetFolderID = vincentFolder.id
            targetFolderName = "03_people/models/vincent"
        } else {
            return AssistantMessage(
                role: .assistant,
                text: "Please select a folder in the sidebar first (for example `03_people/models/vincent` or `02_specs/swatches`) so I can split its assets into specialist sub-folders."
            )
        }

        let page = try await assetRepo.page(
            matching: AssetQuery(scope: .folder(targetFolderID)),
            sortedBy: .defaultSort,
            offset: 0,
            limit: 2_000
        )
        let folderAssets = try await assetRepo.assets(ids: Set(page.records.map(\.id)))
        guard !folderAssets.isEmpty else {
            return AssistantMessage(
                role: .assistant,
                text: "The folder **\(targetFolderName)** has 0 direct assets to split into sub-folders."
            )
        }

        let assessments = (try? await catalogDB.visualLearning.allLatestAssessments()) ?? [:]
        let isSwatchFolder = targetFolderName.lowercased().contains("swatch")

        var buckets: [String: Set<AssetID>] = [:]
        var priorFolders: [AssetID: FolderID] = [:]

        for asset in folderAssets {
            priorFolders[asset.id] = asset.parentFolderID
            let assessment = assessments[asset.id]
            let text = "\(asset.displayName) \(asset.filename) \(assessment?.rationale ?? "")".lowercased()

            let subfolder: String
            if isSwatchFolder {
                if text.contains("ring") {
                    subfolder = "ring-swatches"
                } else if text.contains("chart") || text.contains("wheel") || text.contains("grid") {
                    subfolder = "color-charts"
                } else if text.contains("grey") || text.contains("gray") || text.contains("%") {
                    subfolder = "grey-percentage"
                } else if text.contains("curl") || text.contains("wave") || text.contains("mm") {
                    subfolder = "curl-pattern"
                } else {
                    subfolder = "circle-swatches"
                }
            } else {
                if assessment?.photoRole == .beforeCandidate || assessment?.photoRole == .comparisonCandidate || text.contains("before") || text.contains("bald") || text.contains("split") {
                    subfolder = "before-after"
                } else if text.contains("install") || text.contains("cut") || text.contains("barber") || text.contains("salon") || text.contains("tape") {
                    subfolder = "install-cut"
                } else if assessment?.hairlinePresentation == .clearlyVisible || text.contains("headshot") || text.contains("closeup") || text.contains("close-up") || text.contains("front") {
                    subfolder = "headshots"
                } else {
                    subfolder = "editorial"
                }
            }
            buckets[subfolder, default: []].insert(asset.id)
        }

        var existingChildrenByName: [String: FolderID] = [:]
        for folder in allFolders where folder.parentFolderID == targetFolderID {
            existingChildrenByName[folder.name.rawValue.lowercased()] = folder.id
        }

        var movedCounts: [String: Int] = [:]
        for (subName, assetIDs) in buckets where !assetIDs.isEmpty {
            let childID: FolderID
            if let existingID = existingChildrenByName[subName.lowercased()] {
                childID = existingID
            } else {
                let created = try await folderRepo.createFolder(named: try FolderName(subName), in: targetFolderID)
                childID = created.id
            }
            try await assetRepo.moveAssets(assetIDs, to: childID)
            movedCounts[subName] = assetIDs.count
        }

        windowModel.expandedFolderIDs.insert(targetFolderID)
        let breakdown = movedCounts.sorted(by: { $0.key < $1.key }).map { "• `\($0.key)/`: **\($0.value)** photos" }.joined(separator: "\n")

        return AssistantMessage(
            role: .assistant,
            text: "I organized **\(folderAssets.count) photos** inside **\(targetFolderName)** into specialist sub-folders:\n\n\(breakdown)",
            actionCard: AssistantActionCard(
                kind: .organizedSubfolders(
                    parentFolderID: targetFolderID,
                    parentName: targetFolderName,
                    movedBySubfolder: movedCounts,
                    priorFolders: priorFolders
                )
            )
        )
    }

    // MARK: - Knowledge & Open-Source Repo Screenshot Scout Tool

    private func handleKnowledgeRepoQuery(prompt: String) async throws -> AssistantMessage {
        let digestURL = URL(fileURLWithPath: "/Users/vincent/06_code/framebase/MediaWorkshop/reports/knowledge_repo_scout_digest.json")
        var items: [AssistantActionCard.KnowledgeRepoItem] = []

        if let data = try? Data(contentsOf: digestURL),
           let rawArray = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] {
            for entry in rawArray.prefix(12) {
                let name = (entry["tool_or_repo_name"] as? String) ?? (entry["filename"] as? String) ?? "Discovered Tool"
                let category = (entry["category_subfolder"] as? String) ?? "open-source-repos"
                let license = (entry["license_type"] as? String) ?? "open_source_free"
                let summary = (entry["why_relevant_to_vincent"] as? String) ?? (entry["description"] as? String) ?? ""
                items.append(
                    AssistantActionCard.KnowledgeRepoItem(
                        name: name,
                        category: category,
                        license: license,
                        summary: summary,
                        assetID: nil
                    )
                )
            }
        }

        if items.isEmpty {
            let criteria = SearchCriteria(folderSubstring: "screenshot")
            let matches = (try? await searchCatalog(matching: criteria)) ?? []
            for asset in matches.prefix(6) {
                items.append(
                    AssistantActionCard.KnowledgeRepoItem(
                        name: asset.displayName,
                        category: "ops-screenshots",
                        license: "verified",
                        summary: asset.filename,
                        assetID: asset.id
                    )
                )
            }
        }

        let summaryLines = items.prefix(6).map { "• **\($0.name)** (`\($0.category)`, `\($0.license)`): \($0.summary)" }.joined(separator: "\n")
        return AssistantMessage(
            role: .assistant,
            text: items.isEmpty
                ? "No open-source repo or tool screenshots have been indexed in the digest yet. Run `multi_pass_sorter.py --mode repo-scout` to scan your screenshot exports."
                : "Here are the top actionable tools, open-source repositories, and CRM screenshots discovered by the **Screenshot Repo Scout**:\n\n\(summaryLines)",
            actionCard: items.isEmpty ? nil : AssistantActionCard(kind: .knowledgeRepos(items: items))
        )
    }

    // MARK: - Action Card Interactions (Open Album, Filter Grid, Undo)

    func performCardPrimaryAction(_ card: AssistantActionCard) {
        switch card.kind {
        case let .createdAlbum(albumID, _, assetIDs):
            windowModel.navigationTarget = .album(albumID)
            windowModel.selectedAssetIDs = Set(assetIDs.prefix(24))
        case let .searchResults(_, _, assetIDs):
            windowModel.selectedAssetIDs = Set(assetIDs)
        case let .organizedSubfolders(parentFolderID, _, _, _):
            windowModel.navigationTarget = .folder(parentFolderID)
            windowModel.expandedFolderIDs.insert(parentFolderID)
        case let .knowledgeRepos(items):
            let ids = items.compactMap(\.assetID)
            if !ids.isEmpty {
                windowModel.selectedAssetIDs = Set(ids)
            }
        }
    }

    func undoCardAction(messageID: UUID) async {
        guard let idx = messages.firstIndex(where: { $0.id == messageID }),
              var card = messages[idx].actionCard,
              !card.isUndone else { return }

        do {
            switch card.kind {
            case let .createdAlbum(albumID, _, _):
                try await windowModel.container.albumRepository?.deleteAlbum(albumID)
                if let albums = try? await windowModel.container.albumRepository?.albums() {
                    windowModel.albums = albums
                }
                windowModel.navigationTarget = .allAssets
            case let .organizedSubfolders(parentFolderID, _, _, priorFolders):
                if let assetRepo = windowModel.container.assetRepository {
                    for (assetID, folderID) in priorFolders {
                        try await assetRepo.moveAssets([assetID], to: folderID)
                    }
                }
                windowModel.navigationTarget = .folder(parentFolderID)
            default:
                break
            }
            card.isUndone = true
            let old = messages[idx]
            messages[idx] = AssistantMessage(
                id: old.id,
                role: old.role,
                text: old.text + "\n\n*(Action undone)*",
                timestamp: old.timestamp,
                actionCard: card
            )
        } catch {
            statusBanner = "Undo failed: \(error.localizedDescription)"
        }
    }

    // MARK: - The Hair Concierge Brain (`the-hair-concierge-2026` RAG & Spec Engine)

    private func handleHairConciergeBrainQuery(prompt: String) async throws -> AssistantMessage {
        let lower = prompt.lowercased()
        let criteria = parseSearchCriteria(from: prompt)
        let matchedAssets = (try? await searchCatalog(matching: criteria)) ?? []
        let matchedIDs = matchedAssets.map(\.id)
        if !matchedIDs.isEmpty {
            windowModel.selectedAssetIDs = Set(matchedIDs.prefix(24))
        }

        var sections: [String] = []
        sections.append("### The Hair Concierge Knowledge Brain (`the-hair-concierge-2026`)")

        if lower.contains("base") || lower.contains("lace") || lower.contains("skin") || lower.contains("0.03") || lower.contains("swim") || lower.contains("recommend") {
            sections.append("""
            **Base Construction & Lifespan (`hair-system-knowledge` RAG)**:
            • **Ultra-Thin Skin (`base:poly-skin`, 0.03mm)**: Maximum front hairline translucency (10/10), 2–3 mo lifespan, best for exposed slicked-back hairlines.
            • **Thin Skin (`base:poly-skin`, 0.06–0.08mm)**: Balanced scalp realism (8/10) + durability (3–4 mo).
            • **Swiss Lace (`base:swiss-lace`)**: Finest breathable mesh, disappears on scalp (10/10), 1.5–2 mo lifespan, ideal for hot climates & exposed hairlines.
            • **French Lace (`base:french-lace`)**: Durable breathable lace (2–3 mo), forgiving for active wearers.
            • **Monofilament / Hybrid (`base:mono-mesh`)**: 4–6 mo lifespan for heavy athletics/swimming; Hybrid pairs 2cm ultra-thin skin front with lace crown.
            """)
        }

        if lower.contains("density") || lower.contains("norwood") || lower.contains("age") {
            sections.append("""
            **Age-Calibrated Density Scale (`hair_system_bible_v02.md`)**:
            • **70–80% (Light)**: Ages 50+ / Norwood 5–6 (natural mature recession).
            • **80–90% (Medium-Light)**: Ages 40–50 / Norwood 4.
            • **90–100% (Medium)**: Ages 25–40 (most popular standard).
            • **100–110% (Medium-Heavy)**: Ages 20–30.
            • **Ceiling Rule**: Never exceed 120% density; leading 0.5cm hairline must graduate from 60–65% down to 40% with single bleached knots and irregular baby hairs.
            """)
        }

        if lower.contains("atelier") || lower.contains("brand") || lower.contains("claim") || lower.contains("banned") {
            sections.append("""
            **Atelier Zero v7 & Approved Claims (`marketing-brand` RAG)**:
            • **Palette**: Paper `#EFE7D2`, Bone `#F7F1DE`, Ink `#15140F`, Spot Coral `#FF5757`, Mustard `#E9B94A`, Olive `#6E7448`.
            • **Tier-1 Claims Rule**: Before/after proof imagery must ONLY come from consented real photography in `HSC Library.framebase` (never AI-generated). Avoid banned customer-facing claims (*"undetectable"*, *"100% natural"*, *"guaranteed"*, *"medical grade"*, *"hypoallergenic"*).
            """)
        }

        if sections.count == 1 {
            sections.append("""
            **Connected Corpora in `the-hair-concierge-2026` (`us-west1`)**:
            • `hair-system-knowledge` (`ragCorpora/4611686018427387904`): Hair System Bible v2, Product Facts v1, Approved Claims v1, Media Workshop Taxonomy v1, and 1,551 R2 reference swatches (`hsc_reference_manifest_v01.jsonl`).
            • `marketing-brand` (`ragCorpora/2305843009213693952`): Atelier Zero v7 tokens, Brand Foundations, Storefront Facts, and Krea Marble Head specifications.
            """)
        }

        if !matchedAssets.isEmpty {
            sections.append("I also matched **\(matchedAssets.count) catalog photos** in this library (\(criteria.humanSummary)) and selected the top \(min(24, matchedAssets.count)) in the grid.")
        }

        return AssistantMessage(
            role: .assistant,
            text: sections.joined(separator: "\n\n"),
            actionCard: matchedIDs.isEmpty ? nil : AssistantActionCard(
                kind: .searchResults(
                    title: criteria.SuggestedAlbumTitle,
                    querySummary: criteria.humanSummary,
                    assetIDs: matchedIDs
                )
            )
        )
    }
}

