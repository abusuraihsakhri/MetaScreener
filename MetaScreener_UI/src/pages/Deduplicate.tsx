

export default function Deduplicate() {
  return (
    <div className="p-8 max-w-5xl mx-auto space-y-6 animate-in fade-in duration-500">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight text-gray-900">Deduplicate</h1>
        <p className="text-gray-500 text-sm">Review algorithm-flagged duplicate pairs and merge or keep them.</p>
      </header>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-8 text-center space-y-4">
        <div className="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto text-3xl">
          ✨
        </div>
        <h2 className="text-xl font-semibold text-gray-900">No duplicates found</h2>
        <p className="text-gray-500 max-w-md mx-auto">
          We scanned 1,248 papers and automatically merged exact matches. There are currently no uncertain duplicates requiring manual review.
        </p>
        <button className="px-4 py-2 mt-4 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-hover shadow-sm transition-colors">
          Run Deep Scan
        </button>
      </div>
    </div>
  );
}
