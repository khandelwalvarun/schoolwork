/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      // Five-step typography scale per the redesign plan. Replaces
      // the previous 22-distinct-size sprawl (text-[10px], text-xs,
      // text-sm, text-base, text-lg, text-xl, text-2xl, text-3xl,
      // text-4xl, text-[11px] etc.). Each name encodes its role; the
      // rule is: pick the role, not the pixel value.
      //
      //   text-meta   uppercase labels, kbd hints, tray meta
      //   text-body   workhorse default
      //   text-prose  multi-paragraph prose (briefs, comments)
      //   text-lede   page lede, drawer lede
      //   text-hero   the rare big numeric (one per page max)
      //
      // Tailwind's stock text-xs/sm/base/lg/etc. still exist; the
      // codemod migrates call sites to the named scale incrementally.
      fontSize: {
        meta:  ["11px", { lineHeight: "14px" }],
        body:  ["13px", { lineHeight: "19px" }],
        prose: ["15px", { lineHeight: "22px" }],
        lede:  ["18px", { lineHeight: "26px" }],
        hero:  ["22px", { lineHeight: "28px" }],
      },
    },
  },
  plugins: [],
};
