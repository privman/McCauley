import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const PROSE_CLASSES = [
  "text-sm",
  "[&>*:first-child]:mt-0",
  "[&>*:last-child]:mb-0",
  "[&_p]:my-2",
  "[&_strong]:font-semibold",
  "[&_em]:italic",
  "[&_code]:font-mono [&_code]:text-xs [&_code]:bg-slate-200 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded",
  "[&_pre]:bg-slate-200 [&_pre]:p-2 [&_pre]:rounded [&_pre]:my-2 [&_pre]:overflow-x-auto",
  "[&_pre>code]:bg-transparent [&_pre>code]:p-0 [&_pre>code]:text-sm",
  "[&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2",
  "[&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2",
  "[&_li]:my-0.5",
  "[&_a]:text-blue-600 [&_a]:underline",
  "[&_blockquote]:border-l-2 [&_blockquote]:border-slate-300 [&_blockquote]:pl-3 [&_blockquote]:italic [&_blockquote]:my-2",
  "[&_h1]:text-base [&_h1]:font-semibold [&_h1]:mt-3 [&_h1]:mb-1",
  "[&_h2]:text-base [&_h2]:font-semibold [&_h2]:mt-3 [&_h2]:mb-1",
  "[&_h3]:font-semibold [&_h3]:mt-3 [&_h3]:mb-1",
  "[&_hr]:my-3 [&_hr]:border-slate-300",
  "[&_table]:my-2 [&_table]:border-collapse",
  "[&_th]:border [&_th]:border-slate-300 [&_th]:px-2 [&_th]:py-1 [&_th]:bg-slate-50",
  "[&_td]:border [&_td]:border-slate-300 [&_td]:px-2 [&_td]:py-1",
].join(" ");

export function Markdown({ children }: { children: string }) {
  return (
    <div className={PROSE_CLASSES}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props) => <a {...props} target="_blank" rel="noopener noreferrer" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
