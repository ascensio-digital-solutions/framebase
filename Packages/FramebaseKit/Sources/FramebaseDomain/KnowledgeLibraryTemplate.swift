import Foundation

/// The canonical folder and tag taxonomy for the Knowledge & Swipe File library
/// (`Knowledge Library.framebase`).
public enum KnowledgeLibraryTemplate {
    public static let name = "Knowledge library"

    public static let folders: [LibraryFolderTemplate] = [
        initial("00_inbox"),
        initial("01_ai_and_automation"),
        initial("01_ai_and_automation/tools"),
        initial("01_ai_and_automation/prompts"),
        initial("01_ai_and_automation/agents"),
        initial("01_ai_and_automation/workflows"),
        initial("02_ui_and_web_design"),
        initial("02_ui_and_web_design/landing_pages"),
        initial("02_ui_and_web_design/hero_sections"),
        initial("02_ui_and_web_design/components"),
        initial("02_ui_and_web_design/mobile_ui"),
        initial("03_design_and_branding"),
        initial("03_design_and_branding/typography"),
        initial("03_design_and_branding/palettes"),
        initial("03_design_and_branding/logos"),
        initial("03_design_and_branding/graphics"),
        initial("04_marketing_and_growth"),
        initial("04_marketing_and_growth/carousels"),
        initial("04_marketing_and_growth/hooks"),
        initial("04_marketing_and_growth/copywriting"),
        initial("04_marketing_and_growth/ad_creatives"),
        initial("05_development_and_code"),
        initial("05_development_and_code/python"),
        initial("05_development_and_code/swift"),
        initial("05_development_and_code/apis"),
        initial("05_development_and_code/architecture"),
        initial("06_reference_screenshots")
    ]

    public static let tagNamespaces: [LibraryTagNamespaceTemplate] = [
        .init(namespace: "pillar", allowedValues: ["knowledge"], allowsCustomValues: false, allowsMultipleValuesPerAsset: false),
        .init(namespace: "topic", allowsCustomValues: true, allowsMultipleValuesPerAsset: true),
        .init(namespace: "tool", allowsCustomValues: true, allowsMultipleValuesPerAsset: true),
        .init(namespace: "app", allowsCustomValues: true, allowsMultipleValuesPerAsset: false),
        .init(namespace: "creator", allowsCustomValues: true, allowsMultipleValuesPerAsset: true),
        .init(namespace: "source", allowedValues: ["instagram", "x-twitter", "youtube", "threads", "linkedin", "web"], allowsCustomValues: true, allowsMultipleValuesPerAsset: false),
        .init(namespace: "format", allowedValues: ["carousel", "single-image", "code-snippet", "diagram"], allowsCustomValues: true, allowsMultipleValuesPerAsset: false)
    ]

    public static var initialFolders: [LibraryFolderTemplate] {
        folders.filter { $0.provisioning == .initial }
    }

    public static func initialTagNames() throws -> [TagName] {
        let controlled = try tagNamespaces.flatMap { namespace in
            try namespace.allowedValues.map { try TagName(namespace: namespace.namespace, value: $0) }
        }
        return controlled.sorted { $0.rawValue < $1.rawValue }
    }

    private static func initial(_ path: String) -> LibraryFolderTemplate {
        LibraryFolderTemplate(path: path.split(separator: "/").map(String.init), provisioning: .initial)
    }
}

