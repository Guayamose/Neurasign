const glyphs: Record<string, string[]> = {
  N: ["10001", "11001", "11001", "10101", "10011", "10011", "10001"],
  E: ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
  U: ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
  R: ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
  A: ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
  S: ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
  I: ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
  G: ["01111", "10000", "10000", "10111", "10001", "10001", "01110"],
};

/** A small vector wordmark, readable without an external font or image request. */
export function Brand({ className = "" }: { className?: string }) {
  return <svg className={`ns-brand ${className}`} viewBox="0 0 213 29" role="img" aria-label="NEURASIGN" fill="currentColor">
    {Array.from("NEURASIGN").flatMap((letter, index) => glyphs[letter].flatMap((row, y) => Array.from(row).flatMap((dot, x) => dot === "1" ? <circle key={`${index}-${x}-${y}`} cx={index * 24 + x * 4 + 2} cy={y * 4 + 2} r="1.35" /> : [])))}
  </svg>;
}

/** Decorative halftone sphere. It represents the identity, never live sensor data. */
export function SignalOrb({ className = "" }: { className?: string }) {
  const dots = [];
  for (let row = 0; row <= 42; row++) {
    const latitude = (row / 42 - .5) * Math.PI * .94;
    for (let column = 0; column <= 58; column++) {
      const longitude = (column / 58 - .5) * Math.PI;
      const x = Math.cos(latitude) * Math.sin(longitude);
      const y = Math.sin(latitude);
      const z = Math.cos(latitude) * Math.cos(longitude);
      const tilt = -.24;
      const rotatedX = x * Math.cos(tilt) - y * Math.sin(tilt);
      const rotatedY = x * Math.sin(tilt) + y * Math.cos(tilt);
      const light = Math.max(.09, .35 + x * .36 - y * .35 + z * .35);
      dots.push(<circle key={`${row}-${column}`} cx={+(260 + rotatedX * 226).toFixed(3)} cy={+(260 + rotatedY * 226).toFixed(3)} r={+(1.15 + z * 1.05).toFixed(3)} opacity={+light.toFixed(3)} />);
    }
  }
  return <svg className={`ns-signal-orb ${className}`} viewBox="0 0 520 520" fill="currentColor" aria-hidden="true" focusable="false">{dots}</svg>;
}
