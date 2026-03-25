/**
 * Heni Kozmetik Homepage - Interactive Enhancements
 * Premium B2B Manufacturing Website
 */

document.addEventListener('DOMContentLoaded', function() {
    
    // ═══════════════════════════════════════════════════
    // NAVBAR SCROLL EFFECT
    // ═══════════════════════════════════════════════════
    const navbar = document.querySelector('.site-header') || document.querySelector('.hp-nav');
    let lastScroll = 0;
    
    window.addEventListener('scroll', function() {
        const currentScroll = window.pageYOffset;
        
        if (currentScroll > 100) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
        
        lastScroll = currentScroll;
    });
    
    // ═══════════════════════════════════════════════════
    // SMOOTH SCROLL FOR ANCHOR LINKS
    // ═══════════════════════════════════════════════════
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            
            // Skip if href is just "#"
            if (href === '#') return;
            
            const target = document.querySelector(href);
            if (target) {
                e.preventDefault();
                const navHeight = navbar ? navbar.offsetHeight : 72;
                const targetPosition = target.offsetTop - navHeight - 20;
                
                window.scrollTo({
                    top: targetPosition,
                    behavior: 'smooth'
                });
            }
        });
    });
    
    // ═══════════════════════════════════════════════════
    // INTERSECTION OBSERVER FOR FADE-IN ANIMATIONS
    // ═══════════════════════════════════════════════════
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -100px 0px'
    };
    
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);
    
    // Add fade-in animation to cards and sections
    const animatedElements = document.querySelectorAll(
        '.industry-card, .cert-card, .capability-item, .export-stat'
    );
    
    animatedElements.forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(30px)';
        el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(el);
    });
    
    // ═══════════════════════════════════════════════════
    // MOBILE MENU TOGGLE (if hamburger is added)
    // ═══════════════════════════════════════════════════
    const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
    const navLinks = document.querySelector('.site-header-links') || document.querySelector('.hp-nav-links');
    
    if (mobileMenuBtn && navLinks) {
        mobileMenuBtn.addEventListener('click', function() {
            navLinks.classList.toggle('active');
            this.classList.toggle('active');
        });
        
        // Close menu when clicking a link
        document.querySelectorAll('.site-header-links a, .hp-nav-links a').forEach(link => {
            link.addEventListener('click', function() {
                navLinks.classList.remove('active');
                mobileMenuBtn.classList.remove('active');
            });
        });
    }
    
    // ═══════════════════════════════════════════════════
    // PARALLAX EFFECT FOR EXPORT SECTION
    // ═══════════════════════════════════════════════════
    const exportSection = document.querySelector('.hp-export');
    
    if (exportSection) {
        window.addEventListener('scroll', function() {
            const scrolled = window.pageYOffset;
            const sectionTop = exportSection.offsetTop;
            const sectionHeight = exportSection.offsetHeight;
            
            if (scrolled > sectionTop - window.innerHeight && scrolled < sectionTop + sectionHeight) {
                const rate = (scrolled - sectionTop + window.innerHeight) * 0.3;
                exportSection.style.backgroundPosition = `center ${rate}px`;
            }
        });
    }
    
    // ═══════════════════════════════════════════════════
    // ACTIVE NAVIGATION HIGHLIGHT
    // ═══════════════════════════════════════════════════
    const sections = document.querySelectorAll('section[id]');
    const navLinksAll = document.querySelectorAll('.site-header-links a[href^="#"], .hp-nav-links a[href^="#"]');
    
    window.addEventListener('scroll', function() {
        const scrollPosition = window.pageYOffset + 150;
        
        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            const sectionHeight = section.offsetHeight;
            const sectionId = section.getAttribute('id');
            
            if (scrollPosition >= sectionTop && scrollPosition < sectionTop + sectionHeight) {
                navLinksAll.forEach(link => {
                    link.classList.remove('active');
                    if (link.getAttribute('href') === `#${sectionId}`) {
                        link.classList.add('active');
                    }
                });
            }
        });
    });
    
    // ═══════════════════════════════════════════════════
    // COUNTER ANIMATION FOR EXPORT STATS
    // ═══════════════════════════════════════════════════
    const statNumbers = document.querySelectorAll('.export-stat-number');
    let hasAnimated = false;
    
    const animateCounter = (element) => {
        const text = element.textContent;
        const number = parseInt(text.replace(/\D/g, ''));
        const suffix = text.replace(/[\d\s]/g, '');
        const duration = 2000;
        const increment = number / (duration / 16);
        let current = 0;
        
        const timer = setInterval(() => {
            current += increment;
            if (current >= number) {
                element.textContent = number + suffix;
                clearInterval(timer);
            } else {
                element.textContent = Math.floor(current) + suffix;
            }
        }, 16);
    };
    
    const statsObserver = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting && !hasAnimated) {
                hasAnimated = true;
                statNumbers.forEach(stat => {
                    animateCounter(stat);
                });
            }
        });
    }, { threshold: 0.5 });
    
    const exportStatsSection = document.querySelector('.export-stats');
    if (exportStatsSection) {
        statsObserver.observe(exportStatsSection);
    }
    
    // ═══════════════════════════════════════════════════
    // CONSOLE MESSAGE
    // ═══════════════════════════════════════════════════
    console.log('%c🏭 Heni Kozmetik - Global Manufacturing Excellence', 
        'font-size: 16px; font-weight: bold; color: #1e3a8a;'
    );
    console.log('%cIndustrial Manufacturing Solutions', 
        'font-size: 12px; color: #334155;'
    );
    
});
