export interface GoogleAiStudioConfig {
  apiKey: string;
  aiGatewayAccountId?: string;
  aiGatewayName?: string;
  fetcher?: typeof fetch;
}

export interface AnalyzeImageVisionParams {
  imageBytes: Uint8Array;
  mimeType: string;
  librarySpace: 'hsc' | 'personal';
  filename?: string;
  ocrHint?: string;
  model?: string;
}

export interface ImageVisionAnalysis {
  topFolder: string;
  subfolder: string;
  proposedTags: string[];
  caption: string;
  ocrText: string;
  hairlineRealismScore?: number;
  baseMaterial?: string;
  confidence: number;
}

export interface EmbedMultimodalParams {
  text?: string;
  imageBytes?: Uint8Array;
  mimeType?: string;
  outputDimensionality?: number;
}

export interface AnalyzeVideoSummaryParams {
  videoBytes: Uint8Array;
  mimeType: string;
  prompt?: string;
}

export interface VideoScene {
  timestamp: string;
  description: string;
}

export interface VideoSummaryResult {
  scenes: VideoScene[];
  transcriptSummary: string;
  rawText?: string;
}

const DEFAULT_GATEWAY_ACCOUNT_ID = '938d6ab84fe239647496cc1540ffa21f';
const DEFAULT_GATEWAY_NAME = 'framebase-vision-dev';

export function uint8ArrayToBase64(bytes: Uint8Array): string {
  if (typeof Buffer !== 'undefined') {
    return Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength).toString('base64');
  }
  let binary = '';
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function cleanJsonText(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.startsWith('```json')) {
    return trimmed.replace(/^```json\s*/i, '').replace(/\s*```$/, '').trim();
  }
  if (trimmed.startsWith('```')) {
    return trimmed.replace(/^```\s*/, '').replace(/\s*```$/, '').trim();
  }
  return trimmed;
}

export class GoogleAiStudioService {
  private readonly apiKey: string;
  private readonly aiGatewayAccountId?: string;
  private readonly aiGatewayName?: string;
  private readonly fetcher: typeof fetch;

  constructor(config: GoogleAiStudioConfig) {
    this.apiKey = config.apiKey;
    this.aiGatewayAccountId = config.aiGatewayAccountId ?? DEFAULT_GATEWAY_ACCOUNT_ID;
    this.aiGatewayName = config.aiGatewayName ?? DEFAULT_GATEWAY_NAME;
    this.fetcher = config.fetcher ?? fetch;
  }

  private async postModelAction(model: string, action: string, body: unknown): Promise<any> {
    const directUrl = `https://generativelanguage.googleapis.com/v1beta/models/${model}:${action}?key=${encodeURIComponent(this.apiKey)}`;
    const useGateway = Boolean(this.aiGatewayAccountId && this.aiGatewayName);

    if (useGateway) {
      const gatewayUrl = `https://gateway.ai.cloudflare.com/v1/${this.aiGatewayAccountId}/${this.aiGatewayName}/google-ai-studio/v1beta/models/${model}:${action}?key=${encodeURIComponent(this.apiKey)}`;
      try {
        const response = await this.fetcher(gatewayUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        if (response.ok) {
          return await response.json();
        }
        console.warn(`AI Gateway returned ${response.status}, falling back to direct Google AI Studio endpoint`);
      } catch (err) {
        console.warn('AI Gateway call failed, falling back to direct Google AI Studio endpoint:', err);
      }
    }

    const directResponse = await this.fetcher(directUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    if (!directResponse.ok) {
      const errText = await directResponse.text().catch(() => '');
      throw new Error(`Google AI Studio error (${directResponse.status}): ${errText}`);
    }

    return await directResponse.json();
  }

  async analyzeImageVision(params: AnalyzeImageVisionParams): Promise<ImageVisionAnalysis> {
    const contextPrompt = [
      `You are an expert visual asset categorization AI for Framebase operating in the "${params.librarySpace}" library space.`,
      params.filename ? `Source filename: ${params.filename}` : '',
      params.ocrHint ? `Pre-extracted OCR text hint: ${params.ocrHint}` : '',
      'Analyze the provided image and return ONLY a valid JSON object with the following fields:',
      '- topFolder (string): primary logical folder category',
      '- subfolder (string): subfolder classification',
      '- proposedTags (array of strings): 3-8 descriptive semantic tags',
      '- caption (string): concise objective description of the visual asset',
      '- ocrText (string): any visible text identified in the image (or empty string)',
      params.librarySpace === 'hsc'
        ? '- hairlineRealismScore (number between 1 and 10, or null): realistic appearance of hair/hairline if visible\n- baseMaterial (string, e.g. "lace", "thin skin", "mono", "hybrid", or null): base material if applicable'
        : '- hairlineRealismScore (null)\n- baseMaterial (null)',
      '- confidence (number between 0.0 and 1.0): confidence score for this classification'
    ].filter(Boolean).join('\n');

    const base64Data = uint8ArrayToBase64(params.imageBytes);
    const body = {
      contents: [
        {
          role: 'user',
          parts: [
            { text: contextPrompt },
            {
              inlineData: {
                mimeType: params.mimeType,
                data: base64Data
              }
            }
          ]
        }
      ],
      generationConfig: {
        responseMimeType: 'application/json'
      }
    };

    const json = await this.postModelAction(params.model ?? 'gemini-3.8-flash', 'generateContent', body);
    const text = json?.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!text) {
      throw new Error('Google AI Studio returned empty or invalid response');
    }

    const parsed = JSON.parse(cleanJsonText(text));
    return {
      topFolder: typeof parsed.topFolder === 'string' ? parsed.topFolder : 'Uncategorized',
      subfolder: typeof parsed.subfolder === 'string' ? parsed.subfolder : '',
      proposedTags: Array.isArray(parsed.proposedTags) ? parsed.proposedTags.map(String) : [],
      caption: typeof parsed.caption === 'string' ? parsed.caption : '',
      ocrText: typeof parsed.ocrText === 'string' ? parsed.ocrText : '',
      hairlineRealismScore: typeof parsed.hairlineRealismScore === 'number' ? parsed.hairlineRealismScore : undefined,
      baseMaterial: typeof parsed.baseMaterial === 'string' ? parsed.baseMaterial : undefined,
      confidence: typeof parsed.confidence === 'number' ? parsed.confidence : 0.8
    };
  }

  async embedMultimodal(params: EmbedMultimodalParams): Promise<number[]> {
    const parts: Array<{ text: string } | { inlineData: { mimeType: string; data: string } }> = [];
    if (params.text) {
      parts.push({ text: params.text });
    }
    if (params.imageBytes) {
      parts.push({
        inlineData: {
          mimeType: params.mimeType ?? 'image/jpeg',
          data: uint8ArrayToBase64(params.imageBytes)
        }
      });
    }
    if (parts.length === 0) {
      parts.push({ text: '' });
    }

    const body = {
      content: {
        parts
      },
      outputDimensionality: params.outputDimensionality ?? 1024
    };

    const json = await this.postModelAction('gemini-embedding-2', 'embedContent', body);
    const values = json?.embedding?.values;
    if (!Array.isArray(values)) {
      throw new Error('Failed to retrieve embedding values from Google AI Studio');
    }
    return values as number[];
  }

  async analyzeVideoSummary(params: AnalyzeVideoSummaryParams): Promise<VideoSummaryResult> {
    const promptText = params.prompt ?? [
      'Extract scene timestamps and transcript summary for this video.',
      'Return a JSON object with:',
      '- scenes: array of objects each having { timestamp: string, description: string }',
      '- transcriptSummary: summary of spoken audio, dialogue, or events'
    ].join('\n');

    const body = {
      contents: [
        {
          role: 'user',
          parts: [
            { text: promptText },
            {
              inlineData: {
                mimeType: params.mimeType,
                data: uint8ArrayToBase64(params.videoBytes)
              }
            }
          ]
        }
      ],
      generationConfig: {
        responseMimeType: 'application/json'
      }
    };

    const json = await this.postModelAction('gemini-omni-1.1-flash', 'generateContent', body);
    const text = json?.candidates?.[0]?.content?.parts?.[0]?.text ?? '';
    let scenes: VideoScene[] = [];
    let transcriptSummary = '';
    try {
      const parsed = JSON.parse(cleanJsonText(text));
      if (Array.isArray(parsed.scenes)) {
        scenes = parsed.scenes.map((s: any) => ({
          timestamp: String(s.timestamp ?? ''),
          description: String(s.description ?? '')
        }));
      }
      if (typeof parsed.transcriptSummary === 'string') {
        transcriptSummary = parsed.transcriptSummary;
      }
    } catch {
      transcriptSummary = text;
    }

    return {
      scenes,
      transcriptSummary,
      rawText: text
    };
  }
}
