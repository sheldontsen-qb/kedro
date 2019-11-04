# Copyright 2018-2019 QuantumBlack Visual Analytics Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
# NONINFRINGEMENT. IN NO EVENT WILL THE LICENSOR OR OTHER CONTRIBUTORS
# BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF, OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# The QuantumBlack Visual Analytics Limited ("QuantumBlack") name and logo
# (either separately or in combination, "QuantumBlack Trademarks") are
# trademarks of QuantumBlack. The License does not grant you any right or
# license to the QuantumBlack Trademarks. You may not use the QuantumBlack
# Trademarks or any confusingly similar mark as a trademark for your product,
#     or use the QuantumBlack Trademarks in any other manner that might cause
# confusion in the marketplace, including but not limited to in advertising,
# on websites, or on software.
#
# See the License for the specific language governing permissions and
# limitations under the License.

"""``PickleS3DataSet`` loads and saves a Python object to a pickle file on S3.
The underlying functionality is supported by the ``pickle`` library, so
it supports all allowed options for loading and saving pickle files.
"""
import copy
import pickle
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any, Dict, Optional

from s3fs.core import S3FileSystem

from kedro.io.core import AbstractVersionedDataSet, DataSetError, Version


class PickleS3DataSet(AbstractVersionedDataSet):
    """``PickleS3DataSet`` loads and saves a Python object to a
        pickle file on S3. The underlying functionality is
        supported by the pickle library, so it supports all
        allowed options for loading and saving pickle files.

        Example:
        ::

            >>> from kedro.io import PickleS3DataSet
            >>> import pandas as pd
            >>>
            >>> dummy_data =  pd.DataFrame({'col1': [1, 2],
            >>>                             'col2': [4, 5],
            >>>                             'col3': [5, 6]})
            >>> data_set = PickleS3DataSet(filepath="data.pkl",
            >>>                            bucket_name="test_bucket",
            >>>                            load_args=None,
            >>>                            save_args=None)
            >>> data_set.save(dummy_data)
            >>> reloaded = data_set.load()
    """

    DEFAULT_LOAD_ARGS = {}  # type: Dict[str, Any]
    DEFAULT_SAVE_ARGS = {}  # type: Dict[str, Any]

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        filepath: str,
        bucket_name: str,
        credentials: Optional[Dict[str, Any]] = None,
        load_args: Optional[Dict[str, Any]] = None,
        save_args: Optional[Dict[str, Any]] = None,
        version: Version = None,
    ) -> None:
        """Creates a new instance of ``PickleS3DataSet`` pointing to a
        concrete file on S3. ``PickleS3DataSet`` uses pickle backend to
        serialise objects to disk:

        pickle.dumps: https://docs.python.org/3/library/pickle.html#pickle.dumps

        and to load serialised objects into memory:

        pickle.loads: https://docs.python.org/3/library/pickle.html#pickle.loads

        Args:
            filepath: path to a pkl file.
            bucket_name: S3 bucket name.
            credentials: Credentials to access the S3 bucket, such as
                ``aws_access_key_id``, ``aws_secret_access_key``.
            load_args: Options for loading pickle files. Refer to the help
                file of ``pickle.loads`` for options.
            save_args: Options for saving pickle files. Refer to the help
                file of ``pickle.dumps`` for options.
            version: If specified, should be an instance of
                ``kedro.io.core.Version``. If its ``load`` attribute is
                None, the latest version will be loaded. If its ``save``
                attribute is None, save version will be autogenerated.
        """
        _credentials = deepcopy(credentials) or {}
        _s3 = S3FileSystem(client_kwargs=_credentials)
        super().__init__(
            PurePosixPath("{}/{}".format(bucket_name, filepath)),
            version,
            exists_function=_s3.exists,
            glob_function=_s3.glob,
        )
        self._bucket_name = bucket_name
        self._credentials = _credentials

        # Handle default load and save arguments
        self._load_args = copy.deepcopy(self.DEFAULT_LOAD_ARGS)
        if load_args is not None:
            self._load_args.update(load_args)
        self._save_args = copy.deepcopy(self.DEFAULT_SAVE_ARGS)
        if save_args is not None:
            self._save_args.update(save_args)

        self._s3 = _s3

    def _describe(self) -> Dict[str, Any]:
        return dict(
            filepath=self._filepath,
            bucket_name=self._bucket_name,
            load_args=self._load_args,
            save_args=self._save_args,
            version=self._version,
        )

    def _load(self) -> Any:
        load_path = str(self._get_load_path())

        with self._s3.open(load_path, mode="rb") as s3_file:
            return pickle.loads(s3_file.read(), **self._load_args)

    def _save(self, data: Any) -> None:
        save_path = str(self._get_save_path())
        try:
            bytes_object = pickle.dumps(data, **self._save_args)
        except Exception:  # pylint: disable=broad-except
            # Checks if the error is due to serialisation or not
            try:
                pickle.dumps(data)
            except Exception:
                raise DataSetError(
                    "{} cannot be serialized. {} can only be used with "
                    "serializable data".format(
                        str(data.__class__), str(self.__class__.__name__)
                    )
                )
            else:
                raise  # pragma: no cover

        with self._s3.open(save_path, mode="wb") as s3_file:
            s3_file.write(bytes_object)

    def _exists(self) -> bool:
        load_path = str(self._get_load_path())
        return self._s3.isfile(load_path)
