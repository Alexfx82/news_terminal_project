def render_hot_board(topics, width, max_rows, show_translation=False):
    lines = [mid_border(width)]
    title = "⚡ BREAKING NEWS  |  LIVE HOT TOPICS  |  {} SLOTS".format(max_rows)
    lines.append(box_line(title, width))
    lines.append(mid_border(width))

    for topic in topics[:max_rows]:
        lines.append(_format_hot_line(topic, width, show_translation))

    for _ in range(len(topics), max_rows):
        lines.append(box_line("", width))

    lines.append(mid_border(width))
    return lines
