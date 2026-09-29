import React, { useState } from 'react';
import {
  Download,
  Smartphone,
  Check,
  Copy,
  ExternalLink,
  X,
  Share2,
  Package,
  Layers,
  ArrowRight,
  Terminal,
} from 'lucide-react';
import { usePWAInstall } from '../hooks/usePWAInstall';

interface DownloadModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const DownloadModal: React.FC<DownloadModalProps> = ({ isOpen, onClose }) => {
  const { isInstallable, isInstalled, isAndroid, isIOS, install } = usePWAInstall();
  const [copied, setCopied] = useState(false);
  const [selectedGuide, setSelectedGuide] = useState<'android' | 'apk' | 'ios' | 'desktop'>('android');

  if (!isOpen) return null;

  const currentUrl = window.location.href;

  const handleCopy = () => {
    navigator.clipboard.writeText(currentUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const handleInstallClick = async () => {
    if (isInstallable) {
      await install();
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="w-full max-w-lg bg-[#0d121f] border border-cyan-500/40 rounded-3xl shadow-2xl shadow-cyan-950/50 overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-5 py-3.5 bg-gradient-to-r from-cyan-950/60 via-slate-900 to-indigo-950/60 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center">
              <Download className="w-4 h-4 text-cyan-400" />
            </div>
            <div>
              <h2 className="font-bold text-sm text-white flex items-center gap-1.5">
                Download & Install DeltaPro
                <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-cyan-500/20 text-cyan-300">
                  Android App
                </span>
              </h2>
              <p className="text-[11px] text-slate-400">
                Install as a standalone native app on phone or desktop
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body (Scrollable) */}
        <div className="p-4 overflow-y-auto space-y-4 text-xs font-mono">
          {/* Quick Install Banner if Browser Supports Direct Prompt */}
          {isInstallable && (
            <div className="p-3.5 rounded-2xl bg-gradient-to-r from-cyan-600/30 to-blue-600/30 border border-cyan-500/60 flex items-center justify-between">
              <div>
                <span className="font-bold text-white text-sm font-sans block">
                  1-Click Direct Install Ready!
                </span>
                <span className="text-[11px] text-cyan-300 font-sans">
                  Your browser supports native 1-tap app installation.
                </span>
              </div>
              <button
                onClick={handleInstallClick}
                className="px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold font-sans text-xs shadow-lg shadow-cyan-500/30 flex items-center gap-1.5 transition-all"
              >
                <Download className="w-4 h-4" />
                <span>Install Now</span>
              </button>
            </div>
          )}

          {isInstalled && (
            <div className="p-3 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 flex items-center gap-2">
              <Check className="w-4 h-4" />
              <span>DeltaPro is already installed and running in Standalone mode!</span>
            </div>
          )}

          {/* Share / Open on Phone URL Bar */}
          <div className="p-3 bg-[#080c14] border border-slate-800 rounded-2xl space-y-1.5">
            <span className="text-[10px] text-slate-400 block font-sans">
              Open this link on your Android Phone to install:
            </span>
            <div className="flex items-center gap-2">
              <input
                type="text"
                readOnly
                value={currentUrl}
                className="flex-1 bg-[#05070c] border border-slate-700/80 rounded-xl px-3 py-2 text-[11px] text-cyan-400 select-all font-mono truncate focus:outline-none"
              />
              <button
                onClick={handleCopy}
                className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-sans text-xs font-semibold flex items-center gap-1.5 transition-all shrink-0"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-emerald-400">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy Link</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Guide Selector Tabs */}
          <div className="flex items-center gap-1 bg-[#080c14] p-1 rounded-xl border border-slate-800 text-[11px] font-sans">
            <button
              onClick={() => setSelectedGuide('android')}
              className={`flex-1 py-1.5 rounded-lg font-medium transition-all ${
                selectedGuide === 'android'
                  ? 'bg-cyan-500 text-slate-950 font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Android (WebAPK)
            </button>
            <button
              onClick={() => setSelectedGuide('apk')}
              className={`flex-1 py-1.5 rounded-lg font-medium transition-all ${
                selectedGuide === 'apk'
                  ? 'bg-cyan-500 text-slate-950 font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Build Native .APK
            </button>
            <button
              onClick={() => setSelectedGuide('desktop')}
              className={`flex-1 py-1.5 rounded-lg font-medium transition-all ${
                selectedGuide === 'desktop'
                  ? 'bg-cyan-500 text-slate-950 font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              PC / Mac
            </button>
            <button
              onClick={() => setSelectedGuide('ios')}
              className={`flex-1 py-1.5 rounded-lg font-medium transition-all ${
                selectedGuide === 'ios'
                  ? 'bg-cyan-500 text-slate-950 font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              iOS
            </button>
          </div>

          {/* Guide Content: Android Installation */}
          {selectedGuide === 'android' && (
            <div className="p-3.5 bg-[#090d18] border border-slate-800 rounded-2xl space-y-3 font-sans">
              <span className="font-bold text-xs text-white block">
                How to install on Android (Chrome / Brave / Samsung Internet):
              </span>
              <div className="space-y-2 text-xs text-slate-300">
                <div className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 font-bold text-[10px] flex items-center justify-center shrink-0">
                    1
                  </div>
                  <div>
                    Open Chrome on your Android phone and visit this app URL.
                  </div>
                </div>
                <div className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 font-bold text-[10px] flex items-center justify-center shrink-0">
                    2
                  </div>
                  <div>
                    Tap the <strong>three dots (⋮)</strong> menu in the top right corner of Chrome.
                  </div>
                </div>
                <div className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 font-bold text-[10px] flex items-center justify-center shrink-0">
                    3
                  </div>
                  <div>
                    Tap <strong>"Install app"</strong> or <strong>"Add to Home screen"</strong>.
                  </div>
                </div>
                <div className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 font-bold text-[10px] flex items-center justify-center shrink-0">
                    4
                  </div>
                  <div>
                    Android automatically generates a <strong>native WebAPK</strong> with full app permissions, standalone fullscreen mode, and app drawer icon!
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Guide Content: Build Native .APK with Bubblewrap / Capacitor */}
          {selectedGuide === 'apk' && (
            <div className="p-3.5 bg-[#090d18] border border-slate-800 rounded-2xl space-y-3 font-sans">
              <span className="font-bold text-xs text-white block flex items-center gap-1.5">
                <Package className="w-4 h-4 text-purple-400" />
                Export / Build Standalone Android .APK file:
              </span>
              <p className="text-xs text-slate-300">
                You can wrap this web app into a signed Android APK file using Google's official <strong>Bubblewrap CLI</strong> or <strong>Capacitor</strong>:
              </p>

              <div className="space-y-2 font-mono text-[11px] text-slate-300">
                <div className="p-2 bg-[#05070c] rounded-xl border border-slate-800">
                  <span className="text-slate-500 block text-[10px]">Method 1: Google Bubblewrap (Fastest APK)</span>
                  <code className="text-cyan-400">npx @bubblewrap/cli init --manifest="{currentUrl}manifest.json"</code>
                  <br />
                  <code className="text-emerald-400">npx @bubblewrap/cli build</code>
                </div>

                <div className="p-2 bg-[#05070c] rounded-xl border border-slate-800">
                  <span className="text-slate-500 block text-[10px]">Method 2: PWABuilder (No Code)</span>
                  <span>Visit <a href="https://www.pwabuilder.com" target="_blank" rel="noreferrer" className="text-cyan-400 underline">pwabuilder.com</a>, paste this URL, and click "Generate Android APK".</span>
                </div>
              </div>
            </div>
          )}

          {/* Guide Content: Desktop */}
          {selectedGuide === 'desktop' && (
            <div className="p-3.5 bg-[#090d18] border border-slate-800 rounded-2xl space-y-2 font-sans text-xs text-slate-300">
              <span className="font-bold text-white block">Install on Windows / Mac / Linux:</span>
              <p>
                In Chrome, Edge, or Brave on your computer, click the <strong>Install icon (computer with down arrow)</strong> inside the right side of the URL address bar, then click <strong>"Install"</strong>.
              </p>
              <p className="text-slate-400">
                DeltaPro will launch in its own dedicated terminal window with full desktop hardware acceleration.
              </p>
            </div>
          )}

          {/* Guide Content: iOS */}
          {selectedGuide === 'ios' && (
            <div className="p-3.5 bg-[#090d18] border border-slate-800 rounded-2xl space-y-2 font-sans text-xs text-slate-300">
              <span className="font-bold text-white block">Install on iPhone / iPad (Safari):</span>
              <p>1. Open this link in Safari.</p>
              <p>2. Tap the <strong>Share</strong> button at the bottom of Safari.</p>
              <p>3. Scroll down and tap <strong>"Add to Home Screen"</strong>.</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 bg-[#080c14] border-t border-slate-800 flex items-center justify-between">
          <span className="text-[11px] text-slate-500 font-mono">
            DeltaPro PWA v1.0 • Offline Ready
          </span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-sans text-xs font-semibold transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
