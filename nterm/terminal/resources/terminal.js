(function() {
    'use strict';
    
    let term = null;
    let fitAddon = null;
    let bridge = null;
    let initialized = false;
    
    // DOM elements
    let contextMenu = null;
    let pasteConfirmDialog = null;

    /**
     * Initialize xterm.js terminal
     */
    function initTerminal() {
        // Default theme (Catppuccin Mocha)
        const defaultTheme = {
            background: '#1e1e2e',
            foreground: '#cdd6f4',
            cursor: '#f5e0dc',
            cursorAccent: '#1e1e2e',
            selectionBackground: '#585b70',
            selectionForeground: '#cdd6f4',
            black: '#45475a',
            red: '#f38ba8',
            green: '#a6e3a1',
            yellow: '#f9e2af',
            blue: '#89b4fa',
            magenta: '#f5c2e7',
            cyan: '#94e2d5',
            white: '#bac2de',
            brightBlack: '#585b70',
            brightRed: '#f38ba8',
            brightGreen: '#a6e3a1',
            brightYellow: '#f9e2af',
            brightBlue: '#89b4fa',
            brightMagenta: '#f5c2e7',
            brightCyan: '#94e2d5',
            brightWhite: '#a6adc8',
        };

        // Create terminal
        term = new Terminal({
            cursorBlink: true,
            cursorStyle: 'block',
            fontSize: 14,
            fontFamily: 'JetBrains Mono, Cascadia Code, Consolas, Menlo, monospace',
            fontWeight: 'normal',
            fontWeightBold: 'bold',
            lineHeight: 1.1,
            letterSpacing: 0,
            theme: defaultTheme,
            allowProposedApi: true,
            scrollback: 10000,
            tabStopWidth: 8,
            bellStyle: 'none',
            macOptionIsMeta: true,
            macOptionClickForcesSelection: true,
            rightClickSelectsWord: true,
        });

        // Load addons
        fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);

        const webLinksAddon = new WebLinksAddon.WebLinksAddon();
        term.loadAddon(webLinksAddon);

        const unicode11Addon = new Unicode11Addon.Unicode11Addon();
        term.loadAddon(unicode11Addon);
        term.unicode.activeVersion = '11';

        // Open terminal in container
        const container = document.getElementById('terminal');
        term.open(container);

        // Initial fit
        setTimeout(() => {
            fitAddon.fit();
        }, 0);

        // Handle user input - properly encode UTF-8 to base64
        term.onData(data => {
            if (bridge) {
                // Encode UTF-8 string to base64
                bridge.onData(btoa(unescape(encodeURIComponent(data))));
            }
        });

        // Handle title changes
        term.onTitleChange(title => {
            if (bridge) {
                bridge.onTitleChange(title);
            }
        });

        // Handle resize
        const resizeObserver = new ResizeObserver(entries => {
            if (!initialized) return;

            try {
                fitAddon.fit();
                if (bridge) {
                    bridge.onResize(term.cols, term.rows);
                }
            } catch (e) {
                console.error('Resize error:', e);
            }
        });
        resizeObserver.observe(container);

        // Focus terminal on click
        container.addEventListener('click', () => {
            term.focus();
        });

        initialized = true;
    }

    /**
     * Set up context menu
     */
    function setupContextMenu() {
        contextMenu = document.getElementById('context-menu');
        const container = document.getElementById('terminal');

        // Show context menu on right-click
        container.addEventListener('contextmenu', (e) => {
            e.preventDefault();

            // Update copy item state based on selection
            const copyItem = document.getElementById('ctx-copy');
            const hasSelection = term.hasSelection();

            if (hasSelection) {
                copyItem.classList.remove('disabled');
            } else {
                copyItem.classList.add('disabled');
            }

            // Position menu
            const x = Math.min(e.clientX, window.innerWidth - 180);
            const y = Math.min(e.clientY, window.innerHeight - 120);

            contextMenu.style.left = x + 'px';
            contextMenu.style.top = y + 'px';
            contextMenu.classList.add('visible');
        });

        // Hide context menu on click elsewhere
        document.addEventListener('click', (e) => {
            if (!contextMenu.contains(e.target)) {
                contextMenu.classList.remove('visible');
            }
        });

        // Hide on escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                contextMenu.classList.remove('visible');
                pasteConfirmDialog.classList.remove('visible');
                if (bridge) {
                    bridge.onPasteCancelled();
                }
            }
        });

        // Context menu actions
        document.getElementById('ctx-copy').addEventListener('click', () => {
            contextMenu.classList.remove('visible');
            doCopy();
        });

        document.getElementById('ctx-paste').addEventListener('click', () => {
            contextMenu.classList.remove('visible');
            doPaste();
        });

        document.getElementById('ctx-clear').addEventListener('click', () => {
            contextMenu.classList.remove('visible');
            term.clear();
        });
    }

    /**
     * Set up paste confirmation dialog
     */
    function setupPasteConfirm() {
        pasteConfirmDialog = document.getElementById('paste-confirm');

        document.getElementById('paste-cancel').addEventListener('click', () => {
            pasteConfirmDialog.classList.remove('visible');
            if (bridge) {
                bridge.onPasteCancelled();
            }
            term.focus();
        });

        document.getElementById('paste-ok').addEventListener('click', () => {
            pasteConfirmDialog.classList.remove('visible');
            if (bridge) {
                bridge.onPasteConfirmed();
            }
            term.focus();
        });
    }

    /**
     * Set up keyboard shortcuts
     */
    function setupKeyboardShortcuts() {
        // Attach to terminal's custom key handler
        term.attachCustomKeyEventHandler((e) => {
            // Detect platform for modifier key
            const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
            const modifier = isMac ? e.metaKey : e.ctrlKey;

            // Ctrl+Shift+C or Cmd+C (Mac) - Copy
            if (modifier && e.shiftKey && e.key === 'C') {
                doCopy();
                return false; // Prevent default
            }

            // Ctrl+Shift+V or Cmd+V (Mac) - Paste
            if (modifier && e.shiftKey && e.key === 'V') {
                doPaste();
                return false;
            }

            // Also support Ctrl+C for copy when there's a selection (non-Mac)
            // On Mac, Cmd+C already works natively
            if (!isMac && e.ctrlKey && !e.shiftKey && e.key === 'c' && term.hasSelection()) {
                doCopy();
                return false;
            }

            // Ctrl+V for paste (non-Mac)
            if (!isMac && e.ctrlKey && !e.shiftKey && e.key === 'v') {
                doPaste();
                return false;
            }

            return true; // Allow default handling
        });
    }

    /**
     * Copy terminal selection to clipboard
     */
    function doCopy() {
        if (!term.hasSelection()) {
            return;
        }

        const selection = term.getSelection();

        navigator.clipboard.writeText(selection).then(() => {
            if (bridge) {
                bridge.onSelectionCopied(selection);
            }
        }).catch(err => {
            console.error('Copy failed:', err);
        });
    }

    /**
     * Paste from clipboard (routes through Python for multiline check)
     */
    function doPaste() {
        navigator.clipboard.readText().then(text => {
            if (!text) return;

            // Send to Python for multiline safety check
            if (bridge) {
                bridge.onPasteRequested(btoa(unescape(encodeURIComponent(text))));
            }
        }).catch(err => {
            console.error('Paste failed:', err);
        });
    }

    /**
     * Set up bridge to Python via QWebChannel
     */
    function setupBridge() {
        new QWebChannel(qt.webChannelTransport, function(channel) {
            bridge = channel.objects.bridge;

            // Data from Python to terminal - properly decode UTF-8
            bridge.write_data.connect(function(dataB64) {
                try {
                    // Decode base64 to binary string, then to UTF-8
                    const binaryString = atob(dataB64);
                    const bytes = new Uint8Array(binaryString.length);
                    for (let i = 0; i < binaryString.length; i++) {
                        bytes[i] = binaryString.charCodeAt(i);
                    }
                    const data = new TextDecoder('utf-8').decode(bytes);
                    term.write(data);
                } catch (e) {
                    console.error('Write error:', e);
                }
            });

            // Theme changes
            bridge.apply_theme.connect(function(themeJson) {
                try {
                    const theme = JSON.parse(themeJson);
                    term.options.theme = theme;

                    // Update CSS variables
                    document.documentElement.style.setProperty(
                        '--bg-color',
                        theme.background || '#1e1e2e'
                    );
                    document.body.style.background = theme.background || '#1e1e2e';
                } catch (e) {
                    console.error('Theme error:', e);
                }
            });

            // Font changes
            bridge.set_font.connect(function(family, size) {
                term.options.fontFamily = family;
                term.options.fontSize = size;
                setTimeout(() => fitAddon.fit(), 0);
            });

            // Resize command
            bridge.do_resize.connect(function(cols, rows) {
                term.resize(cols, rows);
            });

            // Overlay control - now with spinner visibility
            bridge.show_overlay.connect(function(message, showSpinner) {
                const overlay = document.getElementById('overlay');
                const text = document.getElementById('overlay-text');
                const spinner = document.getElementById('overlay-spinner');

                text.textContent = message;

                if (showSpinner) {
                    spinner.classList.add('visible');
                } else {
                    spinner.classList.remove('visible');
                }

                overlay.classList.add('visible');
            });

            bridge.hide_overlay.connect(function() {
                const overlay = document.getElementById('overlay');
                overlay.classList.remove('visible');
                term.focus();
            });

            // Focus command
            bridge.focus_terminal.connect(function() {
                term.focus();
            });

            // Clear command
            bridge.clear_terminal.connect(function() {
                term.clear();
            });

            // Copy command (triggered from Python)
            bridge.do_copy.connect(function() {
                doCopy();
            });

            // Direct paste (already confirmed, skip check)
            bridge.do_paste.connect(function(dataB64) {
                try {
                    const data = decodeURIComponent(escape(atob(dataB64)));
                    // Write directly to terminal as if user typed it
                    // This will be picked up by onData handler
                    term.paste(data);
                } catch (e) {
                    console.error('Direct paste error:', e);
                }
            });

            // Show paste confirmation dialog
            bridge.show_paste_confirm.connect(function(preview, lineCount) {
                document.getElementById('paste-line-count').textContent = lineCount;
                document.getElementById('paste-confirm-preview').textContent = preview;
                pasteConfirmDialog.classList.add('visible');

                // Focus the confirm button
                document.getElementById('paste-ok').focus();
            });

            // Hide paste confirmation dialog
            bridge.hide_paste_confirm.connect(function() {
                pasteConfirmDialog.classList.remove('visible');
                term.focus();
            });

            // Notify Python that terminal is ready
            fitAddon.fit();
            bridge.onResize(term.cols, term.rows);
            bridge.onReady();
            term.focus();
        });
    }

    /**
     * Initialize everything when DOM is ready
     */
    function init() {
        initTerminal();
        setupContextMenu();
        setupPasteConfirm();
        setupKeyboardShortcuts();
        setupBridge();
    }

    // Start when DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();