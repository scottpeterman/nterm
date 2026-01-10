(function() {
    'use strict';
    
    let term = null;
    let fitAddon = null;
    let bridge = null;
    let initialized = false;
    
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
        
        // Handle user input
        term.onData(data => {
            if (bridge) {
                bridge.onData(btoa(data));
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
     * Set up bridge to Python via QWebChannel
     */
    function setupBridge() {
        new QWebChannel(qt.webChannelTransport, function(channel) {
            bridge = channel.objects.bridge;
            
            // Data from Python to terminal
            bridge.write_data.connect(function(dataB64) {
                try {
                    const data = atob(dataB64);
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
            
            // Overlay control
            bridge.show_overlay.connect(function(message) {
                const overlay = document.getElementById('overlay');
                const text = document.getElementById('overlay-text');
                text.textContent = message;
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
        setupBridge();
    }
    
    // Start when DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
