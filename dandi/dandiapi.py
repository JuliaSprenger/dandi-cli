from contextlib import contextmanager
import os.path
from pathlib import Path

import requests

from .consts import MAX_CHUNK_SIZE, known_instances_rev
from .core.digests.dandietag import DandiETag
from .girder import keyring_lookup
from . import get_logger
from .utils import USER_AGENT, try_multiple

lgr = get_logger()


# Following class is loosely based on GirderClient, with authentication etc
# being stripped.
# TODO: add copyright/license info
class RESTFullAPIClient(object):
    """A base class for REST clients"""

    def __init__(self, api_url):
        self.api_url = api_url
        self._session = None
        self._headers = {"User-Agent": USER_AGENT}

    @contextmanager
    def session(self, session=None):
        """
        Use a :class:`requests.Session` object for all outgoing requests.
        If `session` isn't passed into the context manager
        then one will be created and yielded. Session objects are useful for enabling
        persistent HTTP connections as well as partially applying arguments to many
        requests, such as headers.

        Note: `session` is closed when the context manager exits, regardless of who
        created it.

        .. code-block:: python

            with client.session() as session:
                session.headers.update({'User-Agent': 'myapp 1.0'})

                for item in items:
                    client.downloadItem(item, fh)

        In the above example, each request will be executed with the User-Agent header
        while reusing the same TCP connection.

        :param session: An existing :class:`requests.Session` object, or None.
        """
        self._session = session if session else requests.Session()

        try:
            yield self._session
        finally:
            # close only if we started a new one
            if not session:
                self._session.close()
            self._session = None

    def _request_func(self, method):
        if self._session is not None:
            return getattr(self._session, method.lower())
        else:
            return getattr(requests, method.lower())

    def send_request(
        self,
        method,
        path,
        parameters=None,
        data=None,
        files=None,
        json=None,
        headers=None,
        json_resp=True,
        **kwargs,
    ):
        """
        This method looks up the appropriate method, constructs a request URL
        from the base URL, path, and parameters, and then sends the request. If
        the method is unknown or if the path is not found, an exception is
        raised, otherwise a JSON object is returned with the response.

        This is a convenience method to use when making basic requests that do
        not involve multipart file data that might need to be specially encoded
        or handled differently.

        :param method: The HTTP method to use in the request (GET, POST, etc.)
        :type method: str
        :param path: A string containing the path elements for this request.
            Note that the path string should not begin or end with the path  separator, '/'.
        :type path: str
        :param parameters: A dictionary mapping strings to strings, to be used
            as the key/value pairs in the request parameters.
        :type parameters: dict
        :param data: A dictionary, bytes or file-like object to send in the body.
        :param files: A dictionary of 'name' => file-like-objects for multipart encoding upload.
        :type files: dict
        :param json: A JSON object to send in the request body.
        :type json: dict
        :param headers: If present, a dictionary of headers to encode in the request.
        :type headers: dict
        :param json_resp: Whether the response should be parsed as JSON. If False, the raw
            response object is returned. To get the raw binary content of the response,
            use the ``content`` attribute of the return value, e.g.

            .. code-block:: python

                resp = client.get('my/endpoint', json_resp=False)
                print(resp.content)  # Raw binary content
                print(resp.headers)  # Dict of headers

        :type json_resp: bool
        """
        if not parameters:
            parameters = {}

        # Look up the HTTP method we need
        f = self._request_func(method)

        url = self.get_url(path)

        # Make the request, passing parameters and authentication info
        _headers = dict(self._headers)
        if headers:
            _headers.update(headers)

        if json_resp and "accept" not in _headers:
            _headers["accept"] = "application/json"

        lgr.debug("%s %s", method.upper(), url)
        try:
            # urllib3's ConnectionPool isn't thread-safe, so we sometimes hit
            # ConnectionErrors on the start of an upload.  Retry when this
            # happens.  Cf. <https://github.com/urllib3/urllib3/issues/951>.
            result = try_multiple(
                5,
                requests.ConnectionError,
                1.1,
                lambda: f(
                    url,
                    params=parameters,
                    data=data,
                    files=files,
                    json=json,
                    headers=_headers,
                    **kwargs,
                ),
            )
        except Exception:
            lgr.exception("HTTP connection failed")
            raise

        lgr.debug("Response: %d", result.status_code)

        # If success, return the json object. Otherwise throw an exception.
        if not result.ok:
            msg = f"Error {result.status_code} while sending {method} request to {url}"
            lgr.error("%s: %s", msg, result.text)
            raise requests.HTTPError(msg, response=result)

        if json_resp:
            if result.text.strip():
                return result.json()
            else:
                return None
        else:
            return result

    def get_url(self, path):
        # Construct the url
        if path.lower().startswith(("http://", "https://")):
            return path
        else:
            return self.api_url.rstrip("/") + "/" + path.lstrip("/")

    def get(self, path, parameters=None, json_resp=True):
        """
        Convenience method to call :py:func:`send_request` with the 'GET' HTTP method.
        """
        return self.send_request("GET", path, parameters, json_resp=json_resp)

    def post(
        self,
        path,
        parameters=None,
        files=None,
        data=None,
        json=None,
        headers=None,
        json_resp=True,
    ):
        """
        Convenience method to call :py:func:`send_request` with the 'POST' HTTP method.
        """
        return self.send_request(
            "POST",
            path,
            parameters,
            files=files,
            data=data,
            json=json,
            headers=headers,
            json_resp=json_resp,
        )

    def put(self, path, parameters=None, data=None, json=None, json_resp=True):
        """
        Convenience method to call :py:func:`send_request` with the 'PUT'
        HTTP method.
        """
        return self.send_request(
            "PUT", path, parameters, data=data, json=json, json_resp=json_resp
        )

    def delete(self, path, parameters=None, json_resp=True):
        """
        Convenience method to call :py:func:`send_request` with the 'DELETE' HTTP method.
        """
        return self.send_request("DELETE", path, parameters, json_resp=json_resp)

    def patch(self, path, parameters=None, data=None, json=None, json_resp=True):
        """
        Convenience method to call :py:func:`send_request` with the 'PATCH' HTTP method.
        """
        return self.send_request(
            "PATCH", path, parameters, data=data, json=json, json_resp=json_resp
        )


class DandiAPIClient(RESTFullAPIClient):
    def __init__(self, api_url, token=None):
        super().__init__(api_url)
        if token is not None:
            self.authenticate(token)

    def authenticate(self, token):
        self._headers["Authorization"] = f"token {token}"

    def dandi_authenticate(self):
        # Shortcut for advanced folks
        api_key = os.environ.get("DANDI_API_KEY", None)
        if api_key:
            self.authenticate(api_key)
            return
        if self.api_url in known_instances_rev:
            client_name = known_instances_rev[self.api_url]
        else:
            raise NotImplementedError("TODO client name derivation for keyring")
        app_id = f"dandi-api-{client_name}"
        keyring_backend, api_key = keyring_lookup(app_id, "key")
        if not api_key:
            api_key = input(f"Please provide API Key for {client_name}: ")
            keyring_backend.set_password(app_id, "key", api_key)
            lgr.debug("Stored key in keyring")
        self.authenticate(api_key)

    def get_asset(self, dandiset_id, version, uuid):
        """

        /dandisets/{version__dandiset__pk}/versions/{version__version}/assets/{uuid}/

        Parameters
        ----------
        dandiset_id
        version
        uuid

        Returns
        -------

        """
        return self.get(f"/dandisets/{dandiset_id}/versions/{version}/assets/{uuid}/")

    def get_dandiset(self, dandiset_id, version):
        return self._migrate_dandiset_metadata(
            self.get(f"/dandisets/{dandiset_id}/versions/{version}/")
        )

    def set_dandiset_metadata(self, dandiset_id, *, metadata):
        # CLI should not update metadata for released dandisets so always "draft"
        return self.put(
            f"/dandisets/{dandiset_id}/versions/draft/",
            json={"metadata": metadata, "name": metadata.get("name", "")},
        )

    def get_dandiset_assets(
        self, dandiset_id, version, page_size=None, path=None, include_metadata=False
    ):
        """ A generator to provide asset records """
        resp = self.get(
            f"/dandisets/{dandiset_id}/versions/{version}/assets/",
            parameters={"page_size": page_size, "path": path},
        )
        while True:
            for asset in resp["results"]:
                if include_metadata:
                    asset["metadata"] = self.get_asset(
                        dandiset_id, version, asset["uuid"]
                    )
                yield asset
            if resp.get("next"):
                resp = self.get(resp["next"])
            else:
                break

    def get_dandiset_and_assets(self, dandiset_id, version, include_metadata=False):
        """This is pretty much an adapter to provide "harmonized" output in both
        girder and DANDI api clients.

        Harmonization should happen toward DANDI API BUT AFAIK it is still influx
        """
        lgr.info(f"Traversing {dandiset_id} (version: {version})")
        dandiset = self.get_dandiset(dandiset_id, version)
        assets = self.get_dandiset_assets(
            dandiset_id, version, include_metadata=include_metadata
        )
        return dandiset, assets

    def get_download_file_iter(
        self, dandiset_id, version, uuid, chunk_size=MAX_CHUNK_SIZE
    ):
        url = self.get_url(
            f"/dandisets/{dandiset_id}/versions/{version}/assets/{uuid}/download/"
        )

        def downloader(start_at=0):
            lgr.debug("Starting download from %s", url)
            headers = None
            if start_at > 0:
                headers = {"Range": f"bytes={start_at}-"}
            result = (self._session if self._session else requests).get(
                url, stream=True, headers=headers
            )
            # TODO: apparently we might need retries here as well etc
            # if result.status_code not in (200, 201):
            result.raise_for_status()

            for chunk in result.iter_content(chunk_size=chunk_size):
                if chunk:  # could be some "keep alive"?
                    yield chunk
            lgr.info("Asset %s successfully downloaded", uuid)

        return downloader

    # TODO: remove when API stabilizes

    # Should perform changes in-place but also return the original record

    @classmethod
    def _migrate_dandiset_metadata(cls, dandiset):
        dandiset_metadata = dandiset.get("metadata", {})
        if not dandiset_metadata:
            return dandiset
        # DANDI API has no versioning yet, and things are in flux.
        # It used to have metadata within a key... just in case let's also
        # be able to handle "old" style
        if "identifier" not in dandiset_metadata and "dandiset" in dandiset_metadata:
            dandiset["metadata"] = dandiset_metadata.pop("dandiset")
        return dandiset

    def upload(self, dandiset_id, version_id, asset_metadata, filepath):
        """
        Parameters
        ----------
        dandiset_id: str
          the ID of the Dandiset to which to upload the file
        version_id: str
          the ID of the version of the Dandiset to which to upload the file
        asset_metadata: dict
          Metadata for the uploaded asset file.  Must include a "path" field
          giving the POSIX path at which the uploaded file will be placed on
          the server.
        filepath: str or PathLike
          the path to the local file to upload
        """
        for _ in self.iter_upload(dandiset_id, version_id, asset_metadata, filepath):
            pass

    def iter_upload(self, dandiset_id, version_id, asset_metadata, filepath):
        """
        Parameters
        ----------
        dandiset_id: str
          the ID of the Dandiset to which to upload the file
        version_id: str
          the ID of the version of the Dandiset to which to upload the file
        asset_metadata: dict
          Metadata for the uploaded asset file.  Must include a "path" field
          giving the POSIX path at which the uploaded file will be placed on
          the server.
        filepath: str or PathLike
          the path to the local file to upload

        Returns
        -------
        a generator of `dict`s containing at least a ``"status"`` key
        """
        from .support.digests import get_digest

        asset_path = asset_metadata["path"]
        yield {"status": "calculating etag"}
        filetag = get_digest(filepath, "dandi-etag")
        lgr.debug("Calculated dandi-etag of %s for %s", filetag, filepath)
        # TODO: Uncomment this once dandi-etags have a DigestType enum value:
        # for digest in asset_metadata.get("digest", []):
        #     if digest["cryptoType"] == ??? :
        #         if digest["value"] != filetag:
        #             raise RuntimeError(
        #                 f"{filepath}: File etag changed; was originally"
        #                 f" {asset_metadata['digest']} but is now {filetag}"
        #             )
        #         break
        try:
            resp = self.post(
                "/blobs/digest/",
                json={"algorithm": "dandi:dandi-etag", "value": filetag},
            )
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                lgr.debug("%s: Blob does not already exist on server", asset_path)
                blob_exists = False
            else:
                raise
        else:
            lgr.debug("%s: Blob is already uploaded to server", asset_path)
            blob_exists = True
            asset_uuid = resp["uuid"]
        if not blob_exists:
            total_size = os.path.getsize(filepath)
            lgr.debug("%s: Beginning upload", asset_path)
            resp = self.post(
                "/uploads/initialize/",
                json={
                    "contentSize": total_size,
                    "digest": {
                        "algorithm": "dandi:dandi-etag",
                        "value": filetag,
                    },
                },
            )
            asset_uuid = resp["uuid"]
            # object_key = resp["multipart_upload"]["object_key"]
            # upload_id = resp["multipart_upload"]["upload_id"]
            parts = resp["multipart_upload"].get("parts", [])
            etagger = DandiETag(total_size)
            if len(parts) != etagger.part_qty:
                raise RuntimeError(
                    f"Server and client disagree on number of parts for upload;"
                    f" server says {len(parts)}, client says {etagger.part_qty}"
                )
            for sp, cp in zip(parts, etagger.get_parts()):
                if sp["size"] != cp.size:
                    raise RuntimeError(
                        f"Server and client disagree on size of upload part"
                        f" {sp['size']['part_number']}; server says"
                        f" {sp['size']}, client says {cp.size}"
                    )
            parts_out = []
            bytes_uploaded = 0
            storage = RESTFullAPIClient("http://nil.nil")
            lgr.debug("Uploading %s in %d parts", filepath, len(parts))
            with storage.session():
                with open(filepath, "rb") as fp:
                    for part in parts:
                        chunk = fp.read(part["size"])
                        if len(chunk) != part["size"]:
                            raise RuntimeError(
                                f"End of file {filepath} reached unexpectedly early"
                            )
                        lgr.debug(
                            "%s: Uploading part %d/%d (%d bytes)",
                            asset_path,
                            part["part_number"],
                            len(parts),
                            part["size"],
                        )
                        r = storage.put(part["upload_url"], data=chunk, json_resp=False)
                        lgr.debug(
                            "%s: Part upload finished ETag=%s Content-Length=%s",
                            asset_path,
                            r.headers.get("ETag"),
                            r.headers.get("Content-Length"),
                        )
                        bytes_uploaded += len(chunk)
                        yield {
                            "status": "uploading",
                            "upload": 100 * bytes_uploaded / total_size,
                            "current": bytes_uploaded,
                        }
                        parts_out.append(
                            {
                                "part_number": part["part_number"],
                                "size": part["size"],
                                "etag": r.headers["ETag"],
                            }
                        )
                lgr.debug("%s: Completing upload", asset_path)
                resp = self.post(
                    f"/uploads/{asset_uuid}/complete/",
                    json={"parts": parts_out},
                )
                lgr.debug(
                    "%s: Announcing completion to %s",
                    asset_path,
                    resp["complete_url"],
                )
                r = storage.post(
                    resp["complete_url"], data=resp["body"], json_resp=False
                )
                lgr.debug(
                    "%s: Upload completed. Response content: %s",
                    asset_path,
                    r.content,
                )
                resp = self.post(f"/uploads/{asset_uuid}/validate/")
                # Another upload may have completed before this one, so the
                # UUID in `resp` may not necessarily be the same as the upload
                # UUID, so we should use `resp["uuid"]` instead from now on.
                asset_uuid = resp["uuid"]
        lgr.debug("%s: Assigning asset blob to dandiset & version", asset_path)
        yield {"status": "producing asset"}
        extant = self.get_asset_bypath(dandiset_id, version_id, asset_path)
        if extant is None:
            self.post(
                f"/dandisets/{dandiset_id}/versions/{version_id}/assets/",
                json={"metadata": asset_metadata, "uuid": asset_uuid},
            )
        else:
            lgr.debug("%s: Asset already exists at path; updating", asset_path)
            self.put(
                f"/dandisets/{dandiset_id}/versions/{version_id}/assets/{extant['uuid']}/",
                json={"metadata": asset_metadata, "uuid": asset_uuid},
            )
        lgr.info("%s: Asset successfully uploaded", asset_path)
        yield {"status": "done"}

    def create_dandiset(self, name, metadata):
        return self.post("/dandisets/", json={"name": name, "metadata": metadata})

    def download_asset(
        self, dandiset_id, version, asset_uuid, filepath, chunk_size=MAX_CHUNK_SIZE
    ):
        downloader = self.get_download_file_iter(
            dandiset_id, version, asset_uuid, chunk_size=chunk_size
        )
        with open(filepath, "wb") as fp:
            for chunk in downloader():
                fp.write(chunk)

    def download_asset_bypath(
        self, dandiset_id, version, asset_path, filepath, chunk_size=MAX_CHUNK_SIZE
    ):
        asset = self.get_asset_bypath(dandiset_id, version, asset_path)
        if asset is None:
            raise RuntimeError(f"No asset found with path {asset_path!r}")
        self.download_asset(
            dandiset_id, version, asset["uuid"], filepath, chunk_size=chunk_size
        )

    def download_assets_directory(
        self, dandiset_id, version, assets_dirpath, dirpath, chunk_size=MAX_CHUNK_SIZE
    ):
        if assets_dirpath and not assets_dirpath.endswith("/"):
            assets_dirpath += "/"
        assets = list(
            self.get_dandiset_assets(dandiset_id, version, path=assets_dirpath)
        )
        for a in assets:
            filepath = Path(dirpath, a["path"][len(assets_dirpath) :])
            filepath.parent.mkdir(parents=True, exist_ok=True)
            self.download_asset(
                dandiset_id, version, a["uuid"], filepath, chunk_size=chunk_size
            )

    def get_asset_bypath(
        self, dandiset_id, version, asset_path, include_metadata=False
    ):
        try:
            # Weed out any assets that happen to have the given path as a
            # proper prefix:
            (asset,) = (
                a
                for a in self.get_dandiset_assets(
                    dandiset_id,
                    version,
                    path=asset_path,
                    include_metadata=include_metadata,
                )
                if a["path"] == asset_path
            )
        except ValueError:
            return None
        else:
            return asset

    def publish_version(self, dandiset_id, base_version_id):
        return self.post(
            f"/dandisets/{dandiset_id}/versions/{base_version_id}/publish/"
        )

    def delete_asset(self, dandiset_id, version_id, asset_uuid):
        self.delete(
            f"/dandisets/{dandiset_id}/versions/{version_id}/assets/{asset_uuid}/"
        )

    def delete_asset_bypath(self, dandiset_id, version_id, asset_path):
        asset = self.get_asset_bypath(dandiset_id, version_id, asset_path)
        if asset is None:
            raise RuntimeError(f"No asset found with path {asset_path!r}")
        self.delete_asset(dandiset_id, version_id, asset["uuid"])
