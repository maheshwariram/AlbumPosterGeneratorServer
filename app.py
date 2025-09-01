import urllib.parse
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import warnings
import requests
from flask import Flask, send_file
from flask import request
from flask_cors import CORS
import math

app = Flask(__name__)
CORS(app)
warnings.filterwarnings("ignore", category=DeprecationWarning)

fonts = {
    "thin": requests.get("https://files.elliotjarnit.dev/fonts/thin.otf"),
    "verylight": requests.get("https://files.elliotjarnit.dev/fonts/verylight.otf"),
    "light": requests.get("https://files.elliotjarnit.dev/fonts/light.otf"),
    "regular": requests.get("https://files.elliotjarnit.dev/fonts/regular.otf"),
    "medium": requests.get("https://files.elliotjarnit.dev/fonts/medium.otf"),
    "semibold": requests.get("https://files.elliotjarnit.dev/fonts/semibold.otf"),
    "bold": requests.get("https://files.elliotjarnit.dev/fonts/bold.otf"),
    "verybold": requests.get("https://files.elliotjarnit.dev/fonts/verybold.otf"),
}


def find_line_split(text):
    middle = len(text) // 2
    before = text.rfind(' ', 0, middle)
    after = text.find(' ', middle + 1)

    if before == -1 and after == -1:
        return middle
    if before == -1:
        return after
    if after == -1:
        return before

    if middle - before < after - middle:
        return before
    else:
        return after


def wrap_text_dynamic(text, font, first_line_max_width, subsequent_max_width):
    """
    wraps text to fit a specific width, with a shorter width for the first line.
    returns a list of lines.
    """
    if font.getbbox(text)[2] <= first_line_max_width:
        return [text]

    words = text.split()
    first_line = ""
    word_index = 0
    for i, word in enumerate(words):
        test_line = first_line + (" " if first_line else "") + word
        if font.getbbox(test_line)[2] > first_line_max_width:
            word_index = i
            break
        first_line = test_line
    else:
        word_index = len(words)

    lines = [first_line]
    remaining_text = " ".join(words[word_index:])

    # now, wrap the rest of the text using the full width
    if remaining_text:
        remaining_lines = [remaining_text]
        while True:
            longest_line = max(remaining_lines, key=lambda line: font.getbbox(line)[2])

            if font.getbbox(longest_line)[2] <= subsequent_max_width:
                break

            split_point = find_line_split(longest_line)
            line1 = longest_line[:split_point].strip()
            line2 = longest_line[split_point:].strip()

            index = remaining_lines.index(longest_line)
            remaining_lines.pop(index)
            remaining_lines.insert(index, line1)
            remaining_lines.insert(index + 1, line2)

        lines.extend(remaining_lines)

    return lines

def wrap_text(text, font, max_width):
    # wraps text to fit a specific width
    if font.getbbox(text)[2] <= max_width:
        return [text]

    lines = [text]
    while True:
        longest_line = max(lines, key=lambda line: font.getbbox(line)[2])
        if font.getbbox(longest_line)[2] <= max_width:
            break

        split_point = find_line_split(longest_line)
        line1 = longest_line[:split_point].strip()
        line2 = longest_line[split_point:].strip()

        index = lines.index(longest_line)
        lines.pop(index)
        lines.insert(index, line1)
        lines.insert(index + 1, line2)
    return lines

def wrap_text_constrained_last_line(text, font, max_width, last_line_max_width):
    lines = wrap_text(text, font, max_width)

    last_line = lines[-1]
    if font.getbbox(last_line)[2] > last_line_max_width:
        # re-wrap the last line with its own constraint
        original_last_line_text = lines.pop(-1)
        # if there were previous lines, add any leftover words from splitting the last line back to them
        if lines:
            words = original_last_line_text.split(' ')
            recombined_line = lines[-1] + " " + words[0]
            if font.getbbox(recombined_line)[2] <= max_width:
                lines[-1] = recombined_line
                original_last_line_text = ' '.join(words[1:])

        new_last_lines = wrap_text(original_last_line_text, font, last_line_max_width)
        lines.extend(new_last_lines)

    return lines

def get_colors(img):
    try:
        paletted = img.convert('P', palette=Image.ADAPTIVE, colors=5)
        palette = paletted.getpalette()
        color_counts = sorted(paletted.getcolors(), reverse=True)
        colors = list()
        for i in range(5):
            palette_index = color_counts[i][1]
            dominant_color = palette[palette_index * 3:palette_index * 3 + 3]
            colors.append(tuple(dominant_color))
    except (IndexError, ValueError):
        paletted = img.convert('P', palette=Image.ADAPTIVE, colors=1)
        palette = paletted.getpalette()
        color_counts = sorted(paletted.getcolors(), reverse=True)
        colors = list()
        if color_counts:
            palette_index = color_counts[0][1]
            dominant_color = palette[palette_index * 3:palette_index * 3 + 3]
            colors.append(tuple(dominant_color))
    return colors


def serve_pil_image(pil_img):
    img_io = BytesIO()
    pil_img.save(img_io, 'JPEG', quality=100)
    img_io.seek(0)
    return send_file(img_io, mimetype='image/jpeg')


def remove_featured(text):
    """ explicitly checking for "feat." or "with"
    coz some songs also have other words in the parentheses (e.g. live, remix)
    """
    if "(feat." in text:
        text = text.split("(feat.")[0].strip()
    if "(with" in text:
        text = text.split("(with")[0].strip()
    return text


def format_time(millis):
    minutes = str(int((millis / (1000 * 60)) % 60))
    seconds = str(int((millis / 1000) % 60))

    if len(seconds) == 1:
        seconds = "0" + seconds

    return minutes + ":" + seconds


def get_uncompressed_image(artwork_url):
    artwork_url = artwork_url.replace("https://is1-ssl.mzstatic.com/image/thumb/",
                                      "https://a5.mzstatic.com/us/r1000/0/")
    artwork_url = artwork_url.replace("/100x100bb.jpg", "")
    artwork_url = artwork_url.replace("/600x600bb.jpg", "")
    return artwork_url


def convert_standard_to_resolution(location, resolution):
    # Location is the pixel location on a 720x960 image
    return location * int(resolution[0]) / 720

def get_largest_resolution(albumart):
    width = albumart.size[0]
    largest_width = width + ((width / 10) * 2)
    # Bandwidth saver
    if largest_width > 1440:
        largest_width = 1440
    # Calculate height with 3:4 ratio
    largest_height = largest_width * (4 / 3)
    return [largest_width, largest_height]


def calculate_optimal_tracklist_layout(tracklist_data, available_width, available_height, image_resolution):
    """
    calculates the best number of rows and font size for the tracklist to ensure readability
    and that all tracks fit within the available space.
    """
    total_tracks = len(tracklist_data)

    font_size = convert_standard_to_resolution(16, image_resolution)
    min_font_size = convert_standard_to_resolution(10, image_resolution)

    while font_size >= min_font_size:
        font = ImageFont.truetype(BytesIO(fonts["regular"].content), int(font_size))
        line_height = font.getbbox("A")[3] + convert_standard_to_resolution(7, image_resolution)

        if line_height <= 0:
            font_size -= 1
            continue

        max_rows = int(available_height / line_height)
        if max_rows == 0:
            font_size -= 1
            continue

        num_cols = math.ceil(total_tracks / max_rows)
        column_width = available_width / num_cols

        longest_track_name = max((item['trackName'] for item in tracklist_data),
                                 key=lambda name: font.getbbox(remove_featured(name))[2])
        required_content_width = font.getbbox(remove_featured(longest_track_name))[2] + font.getbbox("00:00")[
            2] + convert_standard_to_resolution(15, image_resolution)

        if required_content_width <= column_width:
            return max_rows, int(font_size), column_width

        font_size -= 1

    # fallback calculation
    font = ImageFont.truetype(BytesIO(fonts["regular"].content), int(min_font_size))
    line_height = font.getbbox("A")[3] + convert_standard_to_resolution(7, image_resolution)
    max_rows = int(available_height / line_height) if line_height > 0 else 1
    num_cols = math.ceil(total_tracks / max_rows) if max_rows > 0 else total_tracks
    column_width = available_width / num_cols if num_cols > 0 else available_width

    return max_rows if max_rows > 0 else 1, int(min_font_size), column_width

@app.route('/generate', methods=['POST'])
# Parameters: name, artist, year, artwork, tracklist
# Optional: copyright, resolution
def generate_poster():
    data = request.json
    if data["name"] is None:
        return "No name given", 400
    if data["artist"] is None:
        return "No artist given", 400
    if data["year"] is None:
        return "No year given", 400
    if data["artwork"] is None:
        return "No artwork given", 400
    if data["tracklist"] is None:
        return "No tracklist given", 400

    album_artwork_link = get_uncompressed_image(data["artwork"])
    album_name = data["name"]
    album_year = str(data["year"])
    album_artist = data["artist"]
    album_tracklist = data["tracklist"]
    album_copyright = data.get("copyright", "")

    # Open the artwork
    albumart = Image.open(BytesIO(requests.get(album_artwork_link).content))

    if "resolution" in data:
        image_resolution = [int(x) for x in data["resolution"].split("x")]
    else:
        image_resolution = get_largest_resolution(albumart)

    art_size = image_resolution[0] - convert_standard_to_resolution(120, image_resolution)
    albumart.thumbnail((art_size, art_size), Image.Resampling.LANCZOS)

    # Create a new blank image
    poster = Image.new("RGB", (int(image_resolution[0]), int(image_resolution[1])), color=(255, 255, 255))
    posterdraw = ImageDraw.Draw(poster)

    left_margin = convert_standard_to_resolution(60, image_resolution)
    right_margin = convert_standard_to_resolution(660, image_resolution)

    poster.paste(albumart, (int(left_margin),
                            int(convert_standard_to_resolution(60, image_resolution))))

    font_album = ImageFont.truetype(BytesIO(fonts["bold"].content),
                                    convert_standard_to_resolution(35, image_resolution))
    first_line_max_width = right_margin - left_margin - convert_standard_to_resolution(5 * 30 + 15,
                                                                                       image_resolution)
    full_width = right_margin - left_margin

    album_name_lines = wrap_text_dynamic(album_name, font_album, first_line_max_width, full_width)

    album_name_y = convert_standard_to_resolution(695, image_resolution)
    album_line_height = font_album.getbbox("A")[3]
    album_line_spacing = convert_standard_to_resolution(5, image_resolution)

    for i, line in enumerate(album_name_lines):
        current_y = album_name_y + (i * (album_line_height + album_line_spacing))
        posterdraw.text(
            (left_margin, current_y),
            line, font=font_album, fill=(0, 0, 0), anchor='ls'
        )

    last_album_line_y = album_name_y + ((len(album_name_lines) - 1) * (album_line_height + album_line_spacing))

    domcolors = get_colors(albumart)
    color_palette_x = int(right_margin)
    rect_size = int(convert_standard_to_resolution(30, image_resolution))
    for color in domcolors:
        posterdraw.rectangle(
            [(color_palette_x - rect_size, album_name_y - rect_size),
             (color_palette_x, album_name_y)],
            fill=color
        )
        color_palette_x -= rect_size

    artist_year_start_y = last_album_line_y + convert_standard_to_resolution(30, image_resolution)
    font_artist_year = ImageFont.truetype(BytesIO(fonts["semibold"].content),
                                          convert_standard_to_resolution(20, image_resolution))

    year_text = f"{album_year}"
    year_width = font_artist_year.getbbox(year_text)[2]

    artist_last_line_max_width = full_width - year_width - convert_standard_to_resolution(15, image_resolution)

    artist_lines = wrap_text_constrained_last_line(album_artist, font_artist_year, full_width,
                                                   artist_last_line_max_width)

    artist_line_height = font_artist_year.getbbox("A")[3]
    artist_line_spacing = convert_standard_to_resolution(5, image_resolution)

    for i, line in enumerate(artist_lines):
        current_y = artist_year_start_y + (i * (artist_line_height + artist_line_spacing))
        posterdraw.text(
            (left_margin, current_y),
            line, font=font_artist_year, fill=(0, 0, 0), anchor='ls'
        )

    last_artist_line_y = artist_year_start_y + ((len(artist_lines) - 1) * (artist_line_height + artist_line_spacing))
    posterdraw.text(
        (right_margin, last_artist_line_y),
        year_text, font=font_artist_year, fill=(0, 0, 0), anchor='rs'
    )

    divider_y = last_artist_line_y + convert_standard_to_resolution(15, image_resolution)

    posterdraw.rectangle([
        left_margin,
        divider_y,
        right_margin,
        divider_y + convert_standard_to_resolution(5, image_resolution)], fill=(0, 0, 0))

    tracklist_start_y = divider_y + convert_standard_to_resolution(30, image_resolution)
    tracklist_available_width = right_margin - left_margin
    tracklist_available_height = image_resolution[1] - tracklist_start_y - convert_standard_to_resolution(20,
                                                                                                          image_resolution)

    num_rows, font_size, column_width = calculate_optimal_tracklist_layout(
        album_tracklist, tracklist_available_width, tracklist_available_height, image_resolution
    )

    font_tracks = ImageFont.truetype(BytesIO(fonts["regular"].content), font_size)
    line_height = font_tracks.getbbox("A")[3] + convert_standard_to_resolution(7, image_resolution)

    for i, track_item in enumerate(album_tracklist):
        col = i // num_rows
        row = i % num_rows

        x_pos_col_start = left_margin + (col * column_width)
        x_pos_time = x_pos_col_start + column_width - convert_standard_to_resolution(5, image_resolution)
        y_pos = tracklist_start_y + (row * line_height)

        track_name = remove_featured(track_item["trackName"])
        track_time = format_time(track_item["trackTimeMillis"])

        # truncate long track names
        max_track_width = column_width - font_tracks.getbbox(track_time)[2] - convert_standard_to_resolution(15,
                                                                                                          image_resolution)

        if font_tracks.getbbox(track_name)[2] > max_track_width:
            while font_tracks.getbbox(track_name + "...")[2] > max_track_width and len(track_name) > 0:
                track_name = track_name[:-1]
            track_name += "..."

        posterdraw.text((x_pos_col_start, y_pos), track_name, font=font_tracks, fill=(0, 0, 0), anchor='ls')
        posterdraw.text((x_pos_time, y_pos), track_time, font=font_tracks, fill=(0, 0, 0), anchor='rs')

    if album_copyright:
        font_copyright = ImageFont.truetype(BytesIO(fonts["light"].content),
                                            convert_standard_to_resolution(10, image_resolution))
        posterdraw.text(
            (int(image_resolution[0] / 2),
             int(image_resolution[1] - convert_standard_to_resolution(10, image_resolution))),
            album_copyright, font=font_copyright, fill=(0, 0, 0), anchor='ms'
        )

    return serve_pil_image(poster)


if __name__ == '__main__':
    app.run()
