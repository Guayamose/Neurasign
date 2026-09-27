import Image from "next/image";

/** Official approved artwork; source SVG proportions and colors are preserved. */
export function Brand({ className = "", theme = "dark" }: { className?: string; theme?: "dark" | "light" }) {
  return <Image className={`ns-brand ${className}`} src={`/brand/neurasign-${theme}.svg`} alt="NeuraSign" width={956} height={304} unoptimized />;
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
