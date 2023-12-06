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
    if before == -1 or (after != -1 and middle - before >= after - middle):
        middle = after
    else:
        middle = before
    return middle


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
    except:
        paletted = img.convert('P', palette=Image.ADAPTIVE, colors=1)
        palette = paletted.getpalette()
        color_counts = sorted(paletted.getcolors(), reverse=True)
        colors = list()
        for i in range(1):
            palette_index = color_counts[i][1]
            dominant_color = palette[palette_index * 3:palette_index * 3 + 3]
            colors.append(tuple(dominant_color))
    return colors


def serve_pil_image(pil_img):
    img_io = BytesIO()
    pil_img.save(img_io, 'JPEG', quality=100)
    img_io.seek(0)
    return send_file(img_io, mimetype='image/jpeg')


def remove_featured(str):
    if (str.find("(") != -1):
        str = str.split("(")[0].strip()
    return str


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


def get_uncompressed_image(artwork600):
    print(artwork600)
    artwork600 = artwork600.replace("https://is1-ssl.mzstatic.com/image/thumb/", "https://a5.mzstatic.com/us/r1000/0/")
    artwork600 = artwork600.replace("/600x600bb.jpg", "")
    print(artwork600)
    return artwork600


def convert_standard_to_resolution(location, resolution):
    # Location is the pixel location on a 720x960 image
    return location * int(resolution[0]) / 720

def get_largest_resolution(albumart):
    width = albumart.size[0]
    largest_width = width + ((width / 10) * 2)
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

    # Get important details
    album_artwork_link = get_uncompressed_image(data["artwork"].replace('100x100bb.jpg',
                                                                        '600x600bb.jpg'))
    album_name = data["name"]
    album_year = str(data["year"])
    album_artist = data["artist"]
    album_tracklist = data["tracklist"]
    if "copyright" in data:
        album_copyright = data["copyright"]
    else:
        album_copyright = ""

    # Open the artwork
    albumart = Image.open(BytesIO(requests.get(album_artwork_link).content))

    if "resolution" in data:
        image_resolution = data["resolution"]
        image_resolution = image_resolution.split("x")
        image_resolution[0] = int(image_resolution[0])
        image_resolution[1] = int(image_resolution[1])
    else:
        image_resolution = get_largest_resolution(albumart)

    wpercent = (convert_standard_to_resolution(600, image_resolution) / float(albumart.size[0]))
    hsize = int((float(albumart.size[1]) * float(wpercent)))
    albumart = albumart.resize((convert_standard_to_resolution(600, image_resolution), hsize), Image.Resampling.LANCZOS)

    # Create a new blank image
    poster = Image.new("RGB", (int(image_resolution[0]), int(image_resolution[1])), color=(255, 255, 255))
    # Put artwork on blank image
    poster.paste(albumart, (int(convert_standard_to_resolution(60, image_resolution)),
                            int(convert_standard_to_resolution(60, image_resolution))))
    posterdraw = ImageDraw.Draw(poster)
    # Draw seperator
    posterdraw.rectangle([
        convert_standard_to_resolution(60, image_resolution),
        convert_standard_to_resolution(740, image_resolution),
        convert_standard_to_resolution(660, image_resolution),
        convert_standard_to_resolution(745, image_resolution)], fill=(0, 0, 0))
    # Calculate font size for large album names
    length = convert_standard_to_resolution(1000, image_resolution)
    cursize = convert_standard_to_resolution(55, image_resolution)
    twolinesforalbum = False
    while length > convert_standard_to_resolution(480, image_resolution) and cursize >= convert_standard_to_resolution(25, image_resolution):
        font_name = ImageFont.truetype(BytesIO(fonts["verybold"].content), cursize)
        font_year = ImageFont.truetype(BytesIO(fonts["medium"].content), int(cursize / 2) + 5)
        length = font_name.getlength(album_name) + font_year.getlength(album_year) + 77
        cursize -= 1

    if cursize < convert_standard_to_resolution(25, image_resolution) and length > convert_standard_to_resolution(480, image_resolution):
        twolinesforalbum = True
        length = convert_standard_to_resolution(1000, image_resolution)
        cursize = convert_standard_to_resolution(55, image_resolution)

        temp = []
        temp.append(album_name[:find_line_split(album_name)].strip())
        temp.append(album_name[find_line_split(album_name):].strip())
        album_name = temp

        albumnametocompare = ""
        if len(album_name[0]) > len(album_name[1]):
            albumnametocompare = album_name[0]
        else:
            albumnametocompare = album_name[1]

        while length > convert_standard_to_resolution(480, image_resolution) and cursize >= convert_standard_to_resolution(25, image_resolution):
            font_name = ImageFont.truetype(BytesIO(fonts["verybold"].content), cursize)
            font_year = ImageFont.truetype(BytesIO(fonts["medium"].content), int(cursize / 2) + 5)

            length = font_name.getlength(albumnametocompare) + font_year.getlength(
                album_year) + 77
            cursize -= 1

    # Load static fonts
    font_artist = ImageFont.truetype(BytesIO(fonts["semibold"].content), convert_standard_to_resolution(25, image_resolution))
    font_copyright = ImageFont.truetype(BytesIO(fonts["light"].content), convert_standard_to_resolution(10, image_resolution))

    # Get first tracklist
    linesoftracks = 5
    tracklist = create_track_list(linesoftracks, album_tracklist)

    # Extremely complicated font size calculation
    # This is to make sure the tracklist fits on the poster with the biggest font size possible
    # If you want to try and figure out how this works, good luck
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
            max = 0
            for j in range(0, len(tracklist) - 1, linesoftracks * 2):
                for i in range(j, j + linesoftracks):
                    try:
                        if max < font_tracks.getlength(tracklist[i]):
                            max = font_tracks.getlength(tracklist[i])
                    except:
                        break
                length += max + font_times.getlength("00:00") + 30
        if cursize > bestsize:
            bestsize = cursize
            besttracks = tracklist
            bestlinesoftracks = linesoftracks
        linesoftracks += 1
        tracklist = create_track_list(linesoftracks, album_tracklist)
        if linesoftracks > 9:
            break

    # Load best font
    font_tracks = ImageFont.truetype(BytesIO(fonts["regular"].content), bestsize)
    font_times = ImageFont.truetype(BytesIO(fonts["regular"].content), bestsize)
    tracklist = besttracks
    linesoftracks = bestlinesoftracks

    # Put album name on image
    if twolinesforalbum:
        posterdraw.text((convert_standard_to_resolution(65, image_resolution), convert_standard_to_resolution(725, image_resolution) - (font_name.getsize(album_name[0])[1]) + 5),
                        album_name[0],
                        font=font_name,
                        fill=(0, 0, 0),
                        anchor='ls')
        posterdraw.text((convert_standard_to_resolution(65, image_resolution), convert_standard_to_resolution(725, image_resolution)),
                        album_name[1],
                        font=font_name,
                        fill=(0, 0, 0),
                        anchor='ls')
    else:
        posterdraw.text((convert_standard_to_resolution(65, image_resolution), convert_standard_to_resolution(725, image_resolution)),
                        album_name,
                        font=font_name,
                        fill=(0, 0, 0),
                        anchor='ls')
    # Put the year on image
    if twolinesforalbum:
        posterdraw.text((convert_standard_to_resolution(77, image_resolution) + font_name.getlength(albumnametocompare), convert_standard_to_resolution(725, image_resolution)),
                        album_year,
                        font=font_year,
                        fill=(0, 0, 0),
                        anchor='ls')
    else:
        posterdraw.text((convert_standard_to_resolution(77, image_resolution) + font_name.getlength(album_name), convert_standard_to_resolution(725, image_resolution)),
                        album_year,
                        font=font_year,
                        fill=(0, 0, 0),
                        anchor='ls')
    # Get dominant colors
    domcolors = get_colors(albumart)
    # Put dominant color rectangles on poster
    x = int(convert_standard_to_resolution(660, image_resolution))
    rectanglesize = int(convert_standard_to_resolution(30, image_resolution))
    for i in domcolors:
        posterdraw.rectangle([(x - rectanglesize, convert_standard_to_resolution(670, image_resolution)), (x, convert_standard_to_resolution(670, image_resolution) + rectanglesize)],
                             fill=(i))
        x -= rectanglesize
    # Put album artist on poster
    posterdraw.text((convert_standard_to_resolution(660, image_resolution), convert_standard_to_resolution(725, image_resolution)),
                    album_artist,
                    font=font_artist,
                    fill=(0, 0, 0),
                    anchor='rs')
    # Put the tracks onto the poster
    curline = 1
    curx = int(convert_standard_to_resolution(775, image_resolution))
    cury = int(convert_standard_to_resolution(60, image_resolution))
    maxlen = 0
    track = True

    for cur in tracklist:
        if curline > linesoftracks or cur == "-":
            if track:
                cury += maxlen + int(convert_standard_to_resolution(46, image_resolution))
            else:
                cury += maxlen + int(convert_standard_to_resolution(15, image_resolution))
            curx = int(convert_standard_to_resolution(775, image_resolution))
            curline = 1
            maxlen = 0
            track = not track
            if cur == "-":
                continue
        if font_tracks.getlength(cur) > maxlen:
            maxlen = font_tracks.getlength(cur)
        if track:
            posterdraw.text((cury, curx),
                            cur,
                            font=font_tracks,
                            fill=(0, 0, 0),
                            anchor='ls')
        else:
            posterdraw.text((cury, curx),
                            cur,
                            font=font_times,
                            fill=(0, 0, 0),
                            anchor='rs')
        curline += 1
        curx += (int(cursize / 2) + 5) * 2

    if album_copyright != "":
        # Add copyright info on bottom
        posterdraw.text((int(convert_standard_to_resolution(720, image_resolution)) / 2, int(convert_standard_to_resolution(960, image_resolution))),
                        album_copyright,
                        font=font_copyright,
                        fill=(0, 0, 0),
                        anchor='md')

    return serve_pil_image(poster)


if __name__ == '__main__':
    app.run()
