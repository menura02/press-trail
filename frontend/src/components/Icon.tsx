const paths = {
  radar: "M12 12l7-7M5 19a10 10 0 1 1 14 0M8 16a6 6 0 1 1 8 0M12 12h.01",
  overview: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  rss: "M4 4a16 16 0 0 1 16 16M4 11a9 9 0 0 1 9 9M5 20h.01",
  layers: "m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5",
  activity: "M3 12h4l3-7 4 14 3-7h4",
  bell: "M18 8a6 6 0 0 0-12 0v5l-2 3h16l-2-3V8M10 20a2 2 0 0 0 4 0",
  arrow: "M7 17 17 7M7 7h10v10",
  chevron: "m9 6 6 6-6 6",
  globe: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM2 12h20M12 2c5 5 5 15 0 20-5-5-5-15 0-20Z",
};

export function Icon({ name, size = 18 }: { name: keyof typeof paths; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={paths[name]} />
  </svg>;
}
