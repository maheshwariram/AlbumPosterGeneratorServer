import urllib.parse
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import warnings
import requests
from flask import Flask, send_file
from flask import request
from flask_cors import CORS

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


def create_track_list(linesoftracks, response):
    # Get the track list and track times
    # This will create a list with 5 tracks, then those 5 tracks times (in order) and so on.
    # Someone else try to find a better way to do this because this was all I could think of
    tracklist = []
    cur = 1
    savedup = []
    for i in response:
        if cur > linesoftracks:
            cur = 1
            for x in savedup:
                tracklist.append(x)
            savedup = []
        tracklist.append(remove_featured(i["trackName"]))
        savedup.append(format_time(i["trackTimeMillis"]))
        cur += 1
    if len(savedup) > 0:
        tracklist.append("-")
        for x in savedup:
            tracklist.append(x)
    return tracklist


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

    font_album = ImageFont.truetype(BytesIO(fonts["bold"].content),
                                    convert_standard_to_resolution(35, image_resolution))
    first_line_max_width = right_margin - left_margin - convert_standard_to_resolution(5 * 30, image_resolution)
    full_width = right_margin - left_margin

    album_name_lines = wrap_text_dynamic(album_name, font_album, first_line_max_width, full_width)
    num_title_lines = len(album_name_lines)

    album_name_y = convert_standard_to_resolution(695, image_resolution)

    y_offset = 0
    if num_title_lines > 1:
        # if title has multiple lines, calculate the total offset
        line_height = font_album.getbbox("A")[3]
        line_spacing = convert_standard_to_resolution(5, image_resolution)
        y_offset = (num_title_lines - 1) * (line_height + line_spacing)

    artist_year_y = album_name_y + y_offset + convert_standard_to_resolution(30, image_resolution)
    divider_y = artist_year_y + convert_standard_to_resolution(15, image_resolution)
    tracklist_start_y = divider_y + convert_standard_to_resolution(30, image_resolution)

    poster.paste(albumart, (int(left_margin),
                            int(convert_standard_to_resolution(60, image_resolution))))

    line_height = font_album.getbbox("A")[3]
    line_spacing = convert_standard_to_resolution(5, image_resolution)
    for i, line in enumerate(album_name_lines):
        current_y = album_name_y + (i * (line_height + line_spacing))
        posterdraw.text(
            (left_margin, current_y),
            line, font=font_album, fill=(0, 0, 0), anchor='ls'
        )

    artist_year_text = f"{album_artist} ({album_year})"
    font_artist_year = ImageFont.truetype(BytesIO(fonts["semibold"].content),
                                          convert_standard_to_resolution(20, image_resolution))
    posterdraw.text(
        (left_margin, artist_year_y),
        artist_year_text, font=font_artist_year, fill=(0, 0, 0), anchor='ls'
    )

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

    posterdraw.rectangle([
        left_margin,
        divider_y,
        right_margin,
        divider_y + convert_standard_to_resolution(5, image_resolution)], fill=(0, 0, 0))

    linesoftracks = 5
    tracklist = create_track_list(linesoftracks, album_tracklist)

    bestsize = 0
    besttracks = []
    bestlinesoftracks = 0

    while True:
        length = convert_standard_to_resolution(1000, image_resolution)
        cursize = int(convert_standard_to_resolution(17, image_resolution))
        while length > convert_standard_to_resolution(600, image_resolution):
            cursize -= 1
            font_tracks = ImageFont.truetype(BytesIO(fonts["regular"].content), cursize)
            font_times = ImageFont.truetype(BytesIO(fonts["regular"].content), cursize)
            length = 0
            max_len = 0
            for j in range(0, len(tracklist) - 1, linesoftracks * 2):
                for i in range(j, j + linesoftracks):
                    try:
                        if max_len < font_tracks.getbbox(tracklist[i])[2]:
                            max_len = font_tracks.getbbox(tracklist[i])[2]
                    except:
                        break
                length += max_len + font_times.getbbox("00:00")[2] + 30
        if cursize > bestsize:
            bestsize = cursize
            besttracks = tracklist
            bestlinesoftracks = linesoftracks
        linesoftracks += 1
        tracklist = create_track_list(linesoftracks, album_tracklist)

        trackheight = 0
        font_check = ImageFont.truetype(BytesIO(fonts["regular"].content), bestsize)
        for i in range(0, len(tracklist) - 1):
            bbox = font_check.getmask(tracklist[i]).getbbox()
            if bbox:
                trackheight += bbox[3] - bbox[1] + 5
        if trackheight > (image_resolution[1] - tracklist_start_y - convert_standard_to_resolution(20,
                                                                                                   image_resolution)) or linesoftracks > 20:
            break

    # Load best font
    font_tracks = ImageFont.truetype(BytesIO(fonts["regular"].content), bestsize)
    font_times = ImageFont.truetype(BytesIO(fonts["regular"].content), bestsize)
    tracklist = besttracks
    linesoftracks = bestlinesoftracks

    curline = 1
    curx = tracklist_start_y
    cury = int(left_margin)
    maxlen = 0
    track = True

    for cur in tracklist:
        if curline > linesoftracks or cur == "-":
            if track:
                cury += maxlen + int(convert_standard_to_resolution(46, image_resolution))
            else:
                cury += maxlen + int(convert_standard_to_resolution(15, image_resolution))
            curx = tracklist_start_y
            curline = 1
            maxlen = 0
            track = not track
            if cur == "-":
                continue
        if font_tracks.getbbox(cur)[2] > maxlen:
            maxlen = font_tracks.getbbox(cur)[2]
        if track:
            posterdraw.text((cury, curx), cur, font=font_tracks, fill=(0, 0, 0), anchor='ls')
        else:
            posterdraw.text((cury, curx), cur, font=font_times, fill=(0, 0, 0), anchor='rs')
        curline += 1
        curx += (int(bestsize / 2) + 5) * 2

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
