import Foundation

/// The canonical folder and tag taxonomy for the Personal Life Media library
/// (`Personal Library.framebase`).
///
/// Mirrors the `media_workshop` taxonomy while enforcing hard local-only
/// quarantine rules for `06_private_quarantine`.
public enum PersonalLibraryTemplate {
    public static let name = "Personal library"

    /// Folder names that must never be uploaded to Cloudflare R2, Workers AI,
    /// or Google Cloud (`ascensio-media-os`).
    public static let localOnlyQuarantineFolderNames: Set<String> = [
        "06_private_quarantine",
        "sensitive"
    ]

    public static let folders: [LibraryFolderTemplate] = [
        initial("00_inbox"),
        initial("01_people_and_family"),
        initial("01_people_and_family/portraits"),
        initial("01_people_and_family/selfies"),
        initial("01_people_and_family/friends"),
        initial("01_people_and_family/family"),
        initial("02_events_and_milestones"),
        initial("02_events_and_milestones/celebrations"),
        initial("02_events_and_milestones/dining_nightlife"),
        initial("03_travel_and_places"),
        initial("03_travel_and_places/landscapes_nature"),
        initial("03_travel_and_places/urban_architecture"),
        initial("03_travel_and_places/transit_hotel"),
        initial("04_home_and_lifestyle"),
        initial("04_home_and_lifestyle/pets_animals"),
        initial("04_home_and_lifestyle/fitness_health"),
        initial("04_home_and_lifestyle/food_drinks"),
        initial("04_home_and_lifestyle/cars_vehicles"),
        initial("04_home_and_lifestyle/interiors"),
        initial("05_documents_and_receipts"),
        initial("05_documents_and_receipts/ids_cards"),
        initial("05_documents_and_receipts/financial_invoices"),
        initial("05_documents_and_receipts/medical_records"),
        initial("05_documents_and_receipts/contracts"),
        initial("06_private_quarantine")
    ]

    public static let tagNamespaces: [LibraryTagNamespaceTemplate] = [
        .init(namespace: "privacy", allowedValues: ["safe", "local-only", "quarantined"], allowsCustomValues: false, allowsMultipleValuesPerAsset: false),
        .init(namespace: "source", allowedValues: ["iphoto-archive", "iphone", "google-photos", "screenshot", "whatsapp"], allowsCustomValues: false, allowsMultipleValuesPerAsset: false),
        .init(namespace: "year", allowsCustomValues: true, allowsMultipleValuesPerAsset: false),
        .init(namespace: "location", allowsCustomValues: true, allowsMultipleValuesPerAsset: true),
        .init(namespace: "person", allowsCustomValues: true, allowsMultipleValuesPerAsset: true)
    ]

    public static var initialFolders: [LibraryFolderTemplate] {
        folders.filter { $0.provisioning == .initial }
    }

    public static func isLocalOnlyFolder(named name: String) -> Bool {
        localOnlyQuarantineFolderNames.contains(name.lowercased())
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
