from html import escape


def temperature_chart(device_id, before, after, limit):
    def y(value):
        return 210 - min(max(value, 0), 100) * 1.7
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 560 260">'
        '<rect width="560" height="260" fill="#f8fafc"/>'
        '<g font-family="sans-serif" font-size="15" fill="#172033">'
        f'<text x="30" y="30">{escape(device_id)} · Temperature (C)</text>'
        f'<line x1="70" y1="{y(limit)}" x2="490" y2="{y(limit)}" stroke="#b45309" stroke-dasharray="7 5"/>'
        f'<text x="330" y="{y(limit) - 8}">Limit: {limit:g}</text>'
        f'<polyline points="130,{y(before)} 430,{y(after)}" fill="none" stroke="#2563eb" stroke-width="4"/>'
        f'<circle cx="130" cy="{y(before)}" r="6" fill="#2563eb"/>'
        f'<circle cx="430" cy="{y(after)}" r="6" fill="#2563eb"/>'
        f'<text x="100" y="{y(before) - 15}">{before:g}</text>'
        f'<text x="400" y="{y(after) - 15}">{after:g}</text>'
        '<text x="105" y="240">Before</text><text x="410" y="240">After</text>'
        '</g></svg>'
    )
