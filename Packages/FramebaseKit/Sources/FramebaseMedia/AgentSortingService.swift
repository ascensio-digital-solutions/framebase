import Foundation
import FramebaseDomain
import SQLite3

public struct AgentSortingService: Sendable {
    private let ledgerPath: String
    
    public init(ledgerPath: String = "/Users/vMac/00_inbox/Screenshots/AI Sorted/_agent/sort_ledger.sqlite") {
        self.ledgerPath = ledgerPath
    }
    
    public func evaluate(asset: Asset, ocrLines: [OCRLine]?) -> AgentSortingResult? {
        let text = ocrLines?.map { $0.text }.joined(separator: "\n").lowercased() ?? ""
        
        // 1. Check ledger for exact match by SHA-256
        if let ledgerResult = checkLedger(sha256: asset.sha256) {
            return ledgerResult
        }
        
        // 2. Fallback to heuristic rules
        return applyHeuristics(filename: asset.filename.lowercased(), text: text)
    }
    
    private func checkLedger(sha256: String) -> AgentSortingResult? {
        var db: OpaquePointer?
        guard sqlite3_open_v2(ledgerPath, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK else {
            return nil
        }
        defer { sqlite3_close(db) }
        
        let query = "SELECT top_folder, subfolder FROM processed_screenshots WHERE sha256 = ? LIMIT 1"
        var statement: OpaquePointer?
        
        guard sqlite3_prepare_v2(db, query, -1, &statement, nil) == SQLITE_OK else {
            return nil
        }
        defer { sqlite3_finalize(statement) }
        
        sqlite3_bind_text(statement, 1, (sha256 as NSString).utf8String, -1, nil)
        
        if sqlite3_step(statement) == SQLITE_ROW {
            let topFolder = String(cString: sqlite3_column_text(statement, 0))
            let subfolder = String(cString: sqlite3_column_text(statement, 1))
            return AgentSortingResult(topFolder: topFolder, subfolder: subfolder, confidence: 100, reason: "Exact SHA-256 match found in historical ledger")
        }
        
        return nil
    }
    
    private func applyHeuristics(filename: String, text: String) -> AgentSortingResult? {
        let normalizedFilename = filename.replacingOccurrences(of: "-", with: " ").replacingOccurrences(of: "_", with: " ")
        let normalizedText = text.replacingOccurrences(of: "-", with: " ").replacingOccurrences(of: "_", with: " ")
        
        func matches(_ keywords: [String]) -> Bool {
            for k in keywords {
                let target = k.lowercased()
                let targetNorm = target.replacingOccurrences(of: "-", with: " ").replacingOccurrences(of: "_", with: " ")
                if text.contains(target) || filename.contains(target) ||
                   normalizedText.contains(targetNorm) || normalizedFilename.contains(targetNorm) {
                    return true
                }
            }
            return false
        }
        
        if matches(["bysix", "lordhair", "lavivid", "superhairpieces", "toupeec", "hairclub", "wigs.com"]) {
            return AgentSortingResult(topFolder: "01_Web_Design_Storefront", subfolder: "Competitor_Sites", confidence: 92, reason: "Hair replacement competitor storefront or portal")
        }
        
        if matches(["hair solutions co", "hairsolutionsco.com", "onehead", "one head", "serge", "vincent"]) {
            return AgentSortingResult(topFolder: "01_Web_Design_Storefront", subfolder: "Own_Brand_Sites", confidence: 85, reason: "Own brand or portal")
        }
        
        if matches(["google analytics", "google ads", "meta business", "facebook ads", "tiktok ads", "campaign", "roas", "cpc", "conversion rate"]) {
            return AgentSortingResult(topFolder: "02_Marketing_Growth", subfolder: "Ad_Campaigns_Analytics", confidence: 90, reason: "Marketing or ad analytics dashboard")
        }
        
        if matches(["instagram.com", "tiktok.com", "youtube.com", "followers", "likes", "subscribers", "reels", "shorts"]) {
            return AgentSortingResult(topFolder: "02_Marketing_Growth", subfolder: "Social_Media_Profiles", confidence: 85, reason: "Social media profile or engagement metrics")
        }
        
        if matches([
            "salem", "barry", "kevin", "before after", "before_after", "transformation",
            "model portrait", "mannequin hero", "contact sheet", "hero image"
        ]) {
            return AgentSortingResult(topFolder: "02_Marketing_Growth", subfolder: "Model_Portraits_Lifestyle", confidence: 91, reason: "Model portrait, brand persona, or lifestyle transformation asset")
        }
        
        if matches([
            "ghost bond", "ghost bond xl", "ghost bond platinum", "ultra hold", "walker tape",
            "no-shine tape", "c-22", "c22", "action remover", "ghost buster", "knot sealer",
            "extenda-bond", "duo-tac", "scalp protector", "adhesive remover"
        ]) {
            return AgentSortingResult(topFolder: "04_Product_Development", subfolder: "Maintenance_Chemistry", confidence: 96, reason: "Adhesives, solvents, or maintenance chemical formulation")
        }
        
        if matches([
            "hairline", "density", "poly", "lace", "v-loop", "v loop", "bleached knots",
            "swiss lace", "french lace", "0.03mm", "0.06mm", "0.08mm", "bio-skin", "bio skin",
            "thin-skin", "thin skin", "nano-skin", "micro-skin", "monofilament", "fine mono",
            "mono fusion", "graduated hairline", "contour a", "contour c", "knotless", "scalloped"
        ]) {
            return AgentSortingResult(topFolder: "04_Product_Development", subfolder: "System_Specs_Designs", confidence: 94, reason: "Hair system material taxonomy or structural specifications")
        }
        
        if matches(["supplier", "factory", "moq", "wholesale price", "alibaba", "wechat", "shipping cost"]) {
            return AgentSortingResult(topFolder: "04_Product_Development", subfolder: "Supplier_Communications", confidence: 95, reason: "Supplier or factory communication")
        }
        
        if matches(["chatgpt", "claude", "gemini", "midjourney", "prompt", "ai model", "openai", "anthropic"]) {
            return AgentSortingResult(topFolder: "05_AI_Agents_Local_Tooling", subfolder: "ChatGPT_Claude_Gemini", confidence: 98, reason: "AI agent or chat interface")
        }
        
        if matches(["terminal", "xcode", "vscode", "github", "cursor", "python", "swift", "error", "exception", "traceback"]) {
            return AgentSortingResult(topFolder: "05_AI_Agents_Local_Tooling", subfolder: "Dev_Terminal_Errors", confidence: 90, reason: "Development tool or terminal output")
        }
        
        if matches(["receipt", "invoice", "payment", "stripe", "paypal", "charge", "refund", "balance", "bank"]) {
            return AgentSortingResult(topFolder: "06_Admin_Finance", subfolder: "Receipts_Invoices", confidence: 95, reason: "Financial receipt or invoice")
        }
        
        if matches(["password", "login", "auth", "2fa", "verification code", "recovery code"]) {
            return AgentSortingResult(topFolder: "06_Admin_Finance", subfolder: "Passwords_Auth", confidence: 99, reason: "Authentication or login credential")
        }
        
        return nil // Uncategorized
    }
}
