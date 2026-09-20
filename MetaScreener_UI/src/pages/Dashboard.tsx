

const stats = [
  { label: 'Total Identified', value: '1,248', icon: '📄', color: 'text-gray-900', bg: 'bg-gray-100' },
  { label: 'Duplicates Removed', value: '342', icon: '🔁', color: 'text-yellow-600', bg: 'bg-yellow-50' },
  { label: 'Unique Papers', value: '906', icon: '📋', color: 'text-blue-600', bg: 'bg-blue-50' },
  { label: 'Included', value: '45', icon: '✅', color: 'text-emerald-600', bg: 'bg-emerald-50' },
  { label: 'Excluded', value: '620', icon: '❌', color: 'text-red-600', bg: 'bg-red-50' },
  { label: 'Pending', value: '241', icon: '⏳', color: 'text-gray-500', bg: 'bg-gray-50' },
];

export default function Dashboard() {
  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8 animate-in fade-in duration-500">
      
      {/* Header */}
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight text-gray-900">Dashboard</h1>
        <p className="text-gray-500 text-sm max-w-2xl text-balance">
          Overview of your systematic review progress. Track duplicates, screening decisions, and PRISMA flow metrics.
        </p>
      </header>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {stats.map((stat, idx) => (
          <div key={idx} className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex items-start gap-4">
            <div className={`p-3 rounded-lg ${stat.bg} ${stat.color} text-xl shadow-sm border border-black/5`}>
              {stat.icon}
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-gray-500">{stat.label}</p>
              <p className="text-2xl font-semibold text-gray-900 tabular-nums tracking-tight">{stat.value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Progress & PRISMA */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Screening Progress */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Screening Progress</h2>
            <span className="text-sm font-medium text-primary bg-primary/10 px-2.5 py-0.5 rounded-full tabular-nums">
              73%
            </span>
          </div>
          
          <div className="space-y-2">
            <div className="h-2.5 w-full bg-gray-100 rounded-full overflow-hidden flex">
              <div className="h-full bg-emerald-500" style={{ width: '15%' }} title="Included" />
              <div className="h-full bg-red-500" style={{ width: '58%' }} title="Excluded" />
            </div>
            <div className="flex justify-between text-xs font-medium text-gray-500">
              <span>0%</span>
              <span>100%</span>
            </div>
          </div>

          <div className="flex gap-2 flex-wrap">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
              45 Included
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-red-50 text-red-700 border border-red-200">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500"></span>
              620 Excluded
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-gray-50 text-gray-600 border border-gray-200">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400"></span>
              241 Pending
            </span>
          </div>

          <button className="w-full mt-4 py-2.5 bg-white border border-gray-200 shadow-sm rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors">
            Continue Screening
          </button>
        </div>

        {/* PRISMA Flow Summary */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 space-y-6">
          <h2 className="text-lg font-semibold text-gray-900">PRISMA Summary</h2>
          
          <div className="space-y-3">
            {[
              { label: 'Records identified', val: '1,248' },
              { label: 'Duplicates removed', val: '-342' },
              { label: 'Records screened', val: '906', strong: true },
              { label: 'Excluded (screening)', val: '-620' },
              { label: 'Studies included', val: '45', highlight: true },
            ].map((item, i) => (
              <div key={i} className={`flex justify-between items-center py-1.5 ${item.highlight ? 'border-t border-gray-100 mt-2 pt-3' : ''}`}>
                <span className={`text-sm ${item.strong || item.highlight ? 'font-medium text-gray-900' : 'text-gray-600'}`}>
                  {item.label}
                </span>
                <span className={`text-sm tabular-nums ${item.highlight ? 'font-semibold text-primary' : 'text-gray-900'}`}>
                  {item.val}
                </span>
              </div>
            ))}
          </div>

          <button className="w-full py-2.5 bg-primary text-white shadow-sm rounded-lg text-sm font-medium hover:bg-primary-hover transition-colors">
            Download PRISMA Diagram
          </button>
        </div>

      </div>
    </div>
  );
}
