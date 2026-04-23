import { Link } from "react-router-dom";

export default function Settings() {
  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Settings</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Link to="/settings/channels" className="block bg-white border border-gray-200 rounded shadow-sm p-5 hover:bg-gray-50">
          <div className="font-semibold text-lg">Channels</div>
          <div className="text-sm text-gray-600 mt-1">
            Per-channel threshold, mute list, quiet hours, rate limits. Send test messages.
          </div>
        </Link>
        <Link to="/settings/syllabus" className="block bg-white border border-gray-200 rounded shadow-sm p-5 hover:bg-gray-50">
          <div className="font-semibold text-lg">Syllabus calibration</div>
          <div className="text-sm text-gray-600 mt-1">
            Override learning-cycle dates. Mark topics covered / skipped / delayed.
          </div>
        </Link>
      </div>
    </div>
  );
}
