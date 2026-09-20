

export default function Papers() {
  return (
    <div className="p-8 max-w-6xl mx-auto space-y-6 animate-in fade-in duration-500">
      <header className="flex justify-between items-end">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight text-gray-900">Papers</h1>
          <p className="text-gray-500 text-sm">Manage and review imported papers.</p>
        </div>
        <div className="flex gap-3">
          <button className="px-4 py-2 bg-white border border-gray-200 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 shadow-sm transition-colors">
            Import Papers (RIS/CSV)
          </button>
        </div>
      </header>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-gray-100 flex gap-4 bg-gray-50/50">
          <input 
            type="search" 
            placeholder="Search titles or authors..." 
            className="flex-1 px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
          />
          <select className="px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-700 focus:outline-none focus:border-primary">
            <option>All Decisions</option>
            <option>Included</option>
            <option>Excluded</option>
            <option>Pending</option>
          </select>
        </div>
        
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-gray-500 border-b border-gray-200">
            <tr>
              <th className="px-4 py-3 font-medium">Title</th>
              <th className="px-4 py-3 font-medium w-48">Authors</th>
              <th className="px-4 py-3 font-medium w-24">Year</th>
              <th className="px-4 py-3 font-medium w-32">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 text-gray-700">
            {[1, 2, 3, 4, 5].map((i) => (
              <tr key={i} className="hover:bg-gray-50/50 transition-colors">
                <td className="px-4 py-3 font-medium text-gray-900">
                  Example Paper Title {i}: A Systematic Review
                </td>
                <td className="px-4 py-3 truncate max-w-[12rem]">Smith J., Doe A. et al.</td>
                <td className="px-4 py-3 tabular-nums">202{i}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium bg-gray-100 text-gray-600">
                    Pending
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
