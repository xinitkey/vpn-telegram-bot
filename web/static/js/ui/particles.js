const COUNT = 3;
const RED_RATIO = 0.28;
const DIRECTIONS = ['up', 'down', 'left', 'right', 'diag-tr', 'diag-tl', 'diag-br', 'diag-bl'];

function rand(min, max) { return min + Math.random() * (max - min); }

export function initParticles(container = document.querySelector('.bg-mesh'), count = COUNT) {
    if (!container) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const frag = document.createDocumentFragment();
    for (let i = 0; i < count; i++) {
        const p = document.createElement('i');
        p.className = Math.random() < RED_RATIO ? 'particle particle-red' : 'particle';

        const size = 20 + Math.random() * 30;
        const time = 50 + Math.random() * 40;
        const dir = DIRECTIONS[Math.floor(Math.random() * DIRECTIONS.length)];
        const drift = rand(-15, 15);

        let left, top, tx, ty;

        switch (dir) {
            case 'up':
                left = rand(0, 100); top = rand(105, 120);
                tx = drift + 'vw'; ty = -(120 + rand(0, 20)) + 'vh';
                break;
            case 'down':
                left = rand(0, 100); top = rand(-20, -5);
                tx = drift + 'vw'; ty = 120 + rand(0, 20) + 'vh';
                break;
            case 'left':
                left = rand(105, 120); top = rand(0, 100);
                tx = -(120 + rand(0, 20)) + 'vw'; ty = drift + 'vh';
                break;
            case 'right':
                left = rand(-20, -5); top = rand(0, 100);
                tx = 120 + rand(0, 20) + 'vw'; ty = drift + 'vh';
                break;
            case 'diag-tr':
                left = rand(-20, -5); top = rand(105, 120);
                tx = 120 + rand(0, 20) + 'vw'; ty = -(120 + rand(0, 20)) + 'vh';
                break;
            case 'diag-tl':
                left = rand(105, 120); top = rand(105, 120);
                tx = -(120 + rand(0, 20)) + 'vw'; ty = -(120 + rand(0, 20)) + 'vh';
                break;
            case 'diag-br':
                left = rand(-20, -5); top = rand(-20, -5);
                tx = 120 + rand(0, 20) + 'vw'; ty = 120 + rand(0, 20) + 'vh';
                break;
            case 'diag-bl':
                left = rand(105, 120); top = rand(-20, -5);
                tx = -(120 + rand(0, 20)) + 'vw'; ty = 120 + rand(0, 20) + 'vh';
                break;
        }

        p.style.cssText =
            `left:${left.toFixed(1)}%;top:${top.toFixed(1)}%;` +
            `width:${size.toFixed(1)}vw;height:${size.toFixed(1)}vw;` +
            `--p-time:${time.toFixed(1)}s;` +
            `--p-delay:${(-Math.random() * time).toFixed(1)}s;` +
            `--p-tx:${tx};--p-ty:${ty};`;
        frag.appendChild(p);
    }
    container.appendChild(frag);
}