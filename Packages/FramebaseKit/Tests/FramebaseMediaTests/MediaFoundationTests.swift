import FramebaseMedia
import FramebaseDomain
import Testing

@Suite("Media foundation")
struct MediaFoundationTests {
    @Test("Cache defaults match the implementation plan")
    func cacheDefaults() {
        #expect(FramebaseMediaFoundation.defaultMemoryCacheBytes == 268_435_456)
        #expect(FramebaseMediaFoundation.defaultDiskCacheBytes == 5_368_709_120)
        #expect(FramebaseMediaFoundation.thumbnailCacheFormatVersion == 1)
    }

    @Test("AgentSortingService classifies hair replacement materials, chemistry, and personas")
    func agentSortingServiceHeuristics() {
        let service = AgentSortingService(ledgerPath: "/dev/null")
        
        func makeTestAsset(filename: String) -> Asset {
            Asset(
                id: AssetID(),
                filename: filename,
                displayName: filename,
                parentFolderID: FolderID(),
                storageKey: try! AssetStorageKey("ab/\(filename)"),
                fileSize: 2048,
                createdAt: .now,
                modifiedAt: .now,
                importedAt: .now,
                updatedAt: .now
            )
        }
        
        // 1. Material Specs test
        let specAsset = makeTestAsset(filename: "product-thin-skin-0.03mm-hairline.webp")
        let specResult = service.evaluate(asset: specAsset, ocrLines: nil)
        #expect(specResult != nil)
        #expect(specResult?.topFolder == "04_Product_Development")
        #expect(specResult?.subfolder == "System_Specs_Designs")
        
        // 2. Maintenance Chemistry test
        let chemAsset = makeTestAsset(filename: "ghost-bond-xl-adhesive.jpg")
        let chemResult = service.evaluate(asset: chemAsset, ocrLines: nil)
        #expect(chemResult != nil)
        #expect(chemResult?.topFolder == "04_Product_Development")
        #expect(chemResult?.subfolder == "Maintenance_Chemistry")
        
        // 3. Persona / Model Portrait test
        let modelAsset = makeTestAsset(filename: "Barry-retouched.png")
        let modelResult = service.evaluate(asset: modelAsset, ocrLines: nil)
        #expect(modelResult != nil)
        #expect(modelResult?.topFolder == "02_Marketing_Growth")
        #expect(modelResult?.subfolder == "Model_Portraits_Lifestyle")
    }
}

