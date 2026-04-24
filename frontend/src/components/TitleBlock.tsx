/** Shared title renderer — shows the raw title (which may be Devanagari /
 * Sanskrit / English) and, when present and different, the English translation
 * on a subtle second line. Use EVERYWHERE an assignment / grade / comment /
 * message title is rendered, so all non-Latin titles get a consistent English
 * fallback beneath them. */

type Props = {
  title: string | null | undefined;
  titleEn?: string | null;
  className?: string;
  enClassName?: string;
};

export default function TitleBlock({
  title,
  titleEn,
  className = "",
  enClassName = "text-xs text-gray-600 italic mt-0.5",
}: Props) {
  const show = title ?? "";
  const showEn = titleEn && titleEn !== show ? titleEn : null;
  return (
    <div>
      <div className={className}>{show}</div>
      {showEn && <div className={enClassName}>→ {showEn}</div>}
    </div>
  );
}
