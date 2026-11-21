import React, { useState } from 'react';
import {
  Sparkles,
  Search,
  Sliders,
  Zap,
  Globe,
  Radio,
  Copy,
  CheckCircle2,
  ArrowRight,
  Database,
  Terminal,
  Cpu,
  Check
} from 'lucide-react';
import { UserProfile } from '../types';

interface HowItWorksProps {
  userProfile?: UserProfile | null;
  onNavigateToWorkspace?: () => void;
}

export const HowItWorks: React.FC<HowItWorksProps> = ({ userProfile, onNavigateToWorkspace }) => {
  const [activeStep, setActiveStep] = useState<number>(0);
  const [copiedLink, setCopiedLink] = useState(false);
  const [copiedMcp, setCopiedMcp] = useState(false);

  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000';
  const personalLink = userProfile?.dashboard_url || `${origin}/portal?token=YOUR_PERSONAL_TOKEN`;

  const mcpConfig = {
    mcpServers: {
      "acquisition-engine": {
        url: `${origin}/mcp/sse`,
        headers: {
          Authorization: `Bearer ${userProfile?.portal_token || 'YOUR_PERSONAL_TOKEN'}`
        }
      }
    }
  };

  const copyToClipboard = (text: string, type: 'link' | 'mcp') => {
    navigator.clipboard.writeText(text);
    if (type === 'link') {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    } else {
      setCopiedMcp(true);
      setTimeout(() => setCopiedMcp(false), 2000);
    }
  };

  const steps = [
    {
      id: 1,
      title: "1. Natural Language & Source Intelligence",
      tagline: "From conversational queries to precision acquisition",
      icon: Search,
      color: "blue",
      description:
        "When a user asks in plain English (e.g. 'find the movie Iron Man' or 'save this video'), the agent or engine doesn't blindly guess. It evaluates legal OTT/free streaming platforms first, presents options, and if downloading is requested, queries the source intelligence engine to classify the origin.",
      details: [
        "Detects whether input is a direct link, playlist, magnet URL, or conversational search query.",
        "Asks counter-questions (e.g. release year, 4K vs 1080p, audio language, BluRay vs WebRip) to narrow down requirements.",
        "Checks strict SSRF safety firewall before opening any external network connection."
      ],
      sampleQuery: "User: 'Download Iron Man in high quality' → Agent: 'Iron Man (2008). Available on Disney+ OTT or 1080p BluRay (2.1GB) / 720p (950MB). Which quality would you like to acquire?'"
    },
    {
      id: 2,
      title: "2. Smart Format Selector & FFmpeg Muxer",
      tagline: "Foolproof synchronized audio & video every time",
      icon: Sliders,
      color: "purple",
      description:
        "Modern video platforms (like YouTube, Vimeo, and social video) store 1080p/4K video tracks and high-fidelity audio tracks separately. The engine inspects all candidate tracks and automatically selects or muxes them so you never get a muted video.",
      details: [
        "Automatic 'Best Video + Audio' preset detection.",
        "Dedicated 'Audio-Only' extractor for podcasts, music, and voice notes (MP3 / M4A).",
        "Lossless FFmpeg stream muxer combines video and audio into a single MP4 container without re-encoding delays."
      ],
      sampleQuery: "Extracted: [1080p Video Only] + [128k Audio Track] → Engine automatically schedules dual-stream muxing into synchronized MP4."
    },
    {
      id: 3,
      title: "3. High-Speed Concurrent Chunked Downloader",
      tagline: "Maximum line-speed byte-range acceleration",
      icon: Zap,
      color: "amber",
      description:
        "Instead of single-threaded linear downloads that stall on large files, our engine splits supported files into 4-8 parallel byte-range streams, downloading gigabyte files at the physical ceiling of your connection.",
      details: [
        "Concurrent HTTP Range slice downloads assembled in real-time.",
        "Automatic fallback to progressive chunk streaming if the remote server does not advertise Accept-Ranges.",
        "Continuous zero-byte checks and socket retry with exponential backoff."
      ],
      sampleQuery: "File: 1.2 GB Archive → Slices: 4x 300 MB concurrent HTTP threads → 4x acceleration → Reassembled seamlessly into the Vault."
    },
    {
      id: 4,
      title: "4. Headless Browser Media Sniffer",
      tagline: "Captures dynamic JS single-page web media and protected streams",
      icon: Globe,
      color: "emerald",
      description:
        "For complex single-page applications, dynamic players, and anti-bot protected pages (like Pinterest, JS video players, and HTML5 blobs), the engine launches a headless browser to sniff network packets and extract direct media URLs.",
      details: [
        "Intercepts background XHR, Fetch, and media stream requests (HLS, DASH, direct MP4).",
        "Bypasses client-side rendering restrictions and obfuscated JavaScript embeds.",
        "Safely handles redirect hops and redirects through strict loopback IP firewalls."
      ],
      sampleQuery: "Page: https://pinterest.com/pin/... → Sniffer inspects DOM & network requests → Captures 4K direct image / video MP4 payload."
    },
    {
      id: 5,
      title: "5. BitTorrent & Magnet Link Provider",
      tagline: "P2P torrent acquisition with anti-SSRF tracker shields",
      icon: Radio,
      color: "rose",
      description:
        "Supports magnet URIs and .torrent metadata files. The engine inspects torrent infohashes, validates announce trackers against SSRF loopback injection, and manages P2P chunk assembly into private storage.",
      details: [
        "Validates Bencode structure and extracts piece hashes.",
        "Blocks malicious local tracker URLs (e.g. 127.0.0.1, 169.254.169.254, internal subnets).",
        "Tracks piece-level progress, ETA, and verified download state."
      ],
      sampleQuery: "magnet:?xt=urn:btih:3b24... → Engine verifies tracker safety → downloads payload → stores verified artifact in vault."
    },
    {
      id: 6,
      title: "6. Global Content Deduplication (<10ms)",
      tagline: "Zero duplicate bandwidth, 100% private user data isolation",
      icon: Database,
      color: "cyan",
      description:
        "If any user on the platform has previously acquired a file, the engine's Content-Addressable Storage (CAS) recognizes the content hash in under 10 milliseconds and fulfills the request immediately.",
      details: [
        "Instant delivery (<10ms) without consuming external bandwidth or CPU.",
        "Strict multi-tenant isolation: Creates a private artifact record owned exclusively by you.",
        "Zero data leaks: User B receives the file with zero knowledge of User A's identity, timestamps, or job IDs."
      ],
      sampleQuery: "User B requests identical 2GB Linux ISO → Cache Hit in 4ms → User B gets private artifact instantly."
    },
    {
      id: 7,
      title: "7. Autonomous AI Agent Integration",
      tagline: "Seamless MCP Server-Sent Events & REST API integration",
      icon: Cpu,
      color: "indigo",
      description:
        "Any AI agent (Claude Desktop, Cursor, OpenAI Operator, Windsurf, Open-WebUI, AutoGen, CrewAI) can connect directly to your personal workspace using the Model Context Protocol (MCP) or REST API.",
      details: [
        "Real-time Server-Sent Events (SSE) remote transport at /mcp/sse.",
        "Your unique personal link lets you monitor what your agents are downloading in real time.",
        "Interactive Human-in-the-Loop approvals for high-bandwidth or sensitive operations."
      ],
      sampleQuery: "Agent calls inspect_source() → formats returned → agent initiates start_acquisition() → file lands in your personal dashboard."
    }
  ];

  return (
    <div className="max-w-6xl mx-auto space-y-8 pb-16">
      {/* Top Hero Banner */}
      <div className="relative overflow-hidden rounded-2xl border border-electric-500/20 bg-gradient-to-br from-electric-950/40 via-amoled-card to-amoled-card/80 p-8 shadow-2xl backdrop-blur-xl">
        <div className="absolute top-0 right-0 -mt-6 -mr-6 w-56 h-56 rounded-full bg-electric-500/10 blur-3xl pointer-events-none" />
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
          <div className="space-y-3 max-w-2xl">
            <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-electric-500/10 border border-electric-500/30 text-electric-400 text-xs font-mono">
              <Sparkles className="w-3.5 h-3.5" />
              <span>HOW THE AGENT ACQUISITION ENGINE WORKS</span>
            </div>
            <h1 className="text-3xl font-bold tracking-tight text-white">
              Autonomous Media & Document Infrastructure
            </h1>
            <p className="text-sm text-gray-300 leading-relaxed">
              Explore how our high-performance engine classifies, optimizes, accelerates, and secures external downloads for you and your autonomous AI agents.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row gap-3">
            {onNavigateToWorkspace && (
              <button
                onClick={onNavigateToWorkspace}
                className="px-5 py-2.5 rounded-xl bg-electric-600 hover:bg-electric-500 text-white font-medium text-xs flex items-center justify-center space-x-2 transition-all shadow-lg shadow-electric-600/30"
              >
                <span>Launch Workspace</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* User Personal Permanent Link Card */}
      <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/15 p-6 backdrop-blur-lg">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
              <h2 className="text-sm font-semibold text-emerald-300 tracking-wide">
                YOUR UNIQUE PERSONAL DASHBOARD LINK
              </h2>
            </div>
            <p className="text-xs text-gray-300">
              Bookmark this unique URL to access your private downloads, active jobs, and approvals anytime from any device:
            </p>
          </div>

          <div className="flex items-center gap-2 max-w-xl w-full">
            <div className="flex-1 bg-amoled-input border border-amoled-border rounded-lg px-3 py-2 text-xs font-mono text-emerald-400 truncate select-all">
              {personalLink}
            </div>
            <button
              onClick={() => copyToClipboard(personalLink, 'link')}
              className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium flex items-center space-x-1.5 transition-all shrink-0"
            >
              {copiedLink ? <Check className="w-3.5 h-3.5 text-white" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copiedLink ? 'Copied!' : 'Copy Link'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Interactive Architecture Stepper */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Step Selector List */}
        <div className="lg:col-span-5 space-y-2">
          <h3 className="text-xs font-mono text-gray-400 uppercase tracking-wider px-2 mb-3">
            Core Engine Pipeline
          </h3>
          {steps.map((step, idx) => {
            const Icon = step.icon;
            const isSelected = activeStep === idx;
            return (
              <button
                key={step.id}
                onClick={() => setActiveStep(idx)}
                className={`w-full text-left p-4 rounded-xl border transition-all flex items-start space-x-3.5 ${
                  isSelected
                    ? 'bg-amoled-card border-electric-500/50 shadow-[0_0_20px_rgba(59,130,246,0.15)] ring-1 ring-electric-500/30'
                    : 'bg-amoled-card/40 border-amoled-border hover:bg-amoled-hover hover:border-gray-700 text-gray-400'
                }`}
              >
                <div
                  className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${
                    isSelected
                      ? 'bg-electric-600/20 border border-electric-500/40 text-electric-400'
                      : 'bg-amoled-input border border-amoled-border text-gray-400'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className={`text-xs font-semibold ${isSelected ? 'text-white' : 'text-gray-300'}`}>
                    {step.title}
                  </div>
                  <div className="text-[11px] text-gray-400 truncate mt-0.5">
                    {step.tagline}
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Selected Step Deep Dive Card */}
        <div className="lg:col-span-7">
          {(() => {
            const current = steps[activeStep];
            const StepIcon = current.icon;
            return (
              <div className="h-full rounded-2xl border border-amoled-border bg-amoled-card/60 p-8 flex flex-col justify-between backdrop-blur-md">
                <div className="space-y-6">
                  <div className="flex items-center space-x-3">
                    <div className="w-12 h-12 rounded-xl bg-electric-600/20 border border-electric-500/40 flex items-center justify-center text-electric-400">
                      <StepIcon className="w-6 h-6" />
                    </div>
                    <div>
                      <span className="text-[10px] font-mono uppercase tracking-wider text-electric-400">
                        PIPELINE STAGE {current.id} OF {steps.length}
                      </span>
                      <h2 className="text-xl font-bold text-white tracking-tight">
                        {current.title}
                      </h2>
                    </div>
                  </div>

                  <p className="text-sm text-gray-300 leading-relaxed">
                    {current.description}
                  </p>

                  <div className="space-y-2.5">
                    <h4 className="text-xs font-mono uppercase text-gray-400 tracking-wider">
                      Technical Capabilities & Safety
                    </h4>
                    <ul className="space-y-2">
                      {current.details.map((detail, dIdx) => (
                        <li key={dIdx} className="flex items-start space-x-2 text-xs text-gray-300">
                          <CheckCircle2 className="w-4 h-4 text-electric-400 shrink-0 mt-0.5" />
                          <span>{detail}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Sample Query or Technical Execution Box */}
                  <div className="p-4 rounded-xl bg-amoled-input border border-amoled-border font-mono text-xs text-gray-300 space-y-1.5">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wider">
                      Engine Workflow Example
                    </div>
                    <div className="text-electric-300 text-[11px] leading-relaxed">
                      {current.sampleQuery}
                    </div>
                  </div>
                </div>

                <div className="pt-6 border-t border-amoled-border flex items-center justify-between mt-6">
                  <button
                    disabled={activeStep === 0}
                    onClick={() => setActiveStep((prev) => Math.max(0, prev - 1))}
                    className="px-4 py-2 rounded-lg border border-amoled-border text-xs text-gray-300 hover:bg-amoled-hover disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Previous Stage
                  </button>
                  <button
                    disabled={activeStep === steps.length - 1}
                    onClick={() => setActiveStep((prev) => Math.min(steps.length - 1, prev + 1))}
                    className="px-4 py-2 rounded-lg bg-electric-600 hover:bg-electric-500 text-white text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Next Stage
                  </button>
                </div>
              </div>
            );
          })()}
        </div>
      </div>

      {/* Autonomous Agent Setup Snippet */}
      <div className="rounded-2xl border border-amoled-border bg-amoled-card/40 p-8 backdrop-blur-md space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-electric-600/20 border border-electric-500/40 flex items-center justify-center text-electric-400">
              <Terminal className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">Connect Any AI Agent To Your Workspace</h3>
              <p className="text-xs text-gray-400">Add this MCP Server configuration to Claude Desktop, Cursor, or your autonomous agent.</p>
            </div>
          </div>

          <button
            onClick={() => copyToClipboard(JSON.stringify(mcpConfig, null, 2), 'mcp')}
            className="px-3.5 py-1.5 rounded-lg border border-amoled-border bg-amoled-input hover:bg-amoled-hover text-xs text-gray-300 flex items-center space-x-1.5 transition-all"
          >
            {copiedMcp ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copiedMcp ? 'Copied Config!' : 'Copy MCP Config'}</span>
          </button>
        </div>

        <pre className="p-4 rounded-xl bg-amoled-input border border-amoled-border text-[11px] font-mono text-gray-300 overflow-x-auto">
          {JSON.stringify(mcpConfig, null, 2)}
        </pre>
      </div>
    </div>
  );
};
